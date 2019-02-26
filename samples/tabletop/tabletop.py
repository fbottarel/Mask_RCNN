"""
Mask R-CNN
Train on the toy Balloon dataset and implement color splash effect.

Copyright (c) 2018 Matterport, Inc.
Licensed under the MIT License (see LICENSE for details)
Written by Waleed Abdulla

------------------------------------------------------------

Usage: import the module (see Jupyter notebooks for examples), or run from
       the command line as such:

    # Train a new model starting from pre-trained COCO weights
    python3 balloon.py train --dataset=/path/to/balloon/dataset --weights=coco

    # Resume training a model that you had trained earlier
    python3 balloon.py train --dataset=/path/to/balloon/dataset --weights=last

    # Train a new model starting from ImageNet weights
    python3 balloon.py train --dataset=/path/to/balloon/dataset --weights=imagenet

    # Apply color splash to an image
    python3 balloon.py splash --weights=/path/to/weights/file.h5 --image=<URL or path to file>

    # Apply color splash to video using the last weights you trained
    python3 balloon.py splash --weights=last --video=<URL or path to file>
"""

import os
import sys
import json
import datetime
import numpy as np
import skimage.draw

# Root directory of the project
ROOT_DIR = os.path.abspath("../../")

# Import Mask RCNN
sys.path.append(ROOT_DIR)  # To find local version of the library
from mrcnn.config import Config
from mrcnn import model as modellib, utils

# Path to trained weights file
COCO_WEIGHTS_PATH = os.path.join(ROOT_DIR, "mask_rcnn_coco.h5")

# Directory to save logs and model checkpoints, if not provided
# through the command line argument --logs
DEFAULT_LOGS_DIR = os.path.join(ROOT_DIR, "logs")

############################################################
#  Configurations
############################################################


class TabletopConfig(Config):
    """Configuration for training on the toy  dataset.
    Derives from the base Config class and overrides some values.
    """
    # Give the configuration a recognizable name
    NAME = "tabletop"

    # We use a GPU with 12GB memory, which can fit two images.
    # Adjust down if you use a smaller GPU.
    IMAGES_PER_GPU = 3

    # Define number of GPUs to use
    GPU_COUNT = 3

    # Number of classes (including background)
    NUM_CLASSES = 1 + 10  # Background + random YCB objects

    # Specify the backbone network
    BACKBONE = "resnet50"

    # Number of training steps per epoch
    STEPS_PER_EPOCH = 100

    # Number of epochs
    EPOCHS = 150

    # Skip detections with < 90% confidence
    DETECTION_MIN_CONFIDENCE = 0.8

    # Define stages to be fine tuned
    LAYERS_TUNE = '4+'

    # Add some env variables to fix GPU usage
    os.environ['CUDA_DEVICE_ORDER'] = 'PCI_BUS_ID'
    os.environ['CUDA_VISIBLE_DEVICES'] = '0,1,2'


############################################################
#  Dataset
############################################################
class TabletopDataset(utils.Dataset):

    def load_tabletop(self, dataset_root, subset):
        """
        Load the tabletop dataset. Randomly assignes images to train and validation subsets.
        :param dataset_root (string): Root directory of the dataset.
        :param subset (string): Train or validation dataset
        """

        # Training or validation
        assert subset in ["train", "val"]
        subset_dir = os.path.join(dataset_root, subset)

        # Load classes from the json file
        DATASET_JSON_FILENAME = os.path.join(subset_dir, "dataset.json")
        assert os.path.isfile(DATASET_JSON_FILENAME)

        with (open(DATASET_JSON_FILENAME, 'r')) as handle:
            dataset_dict = json.loads(json.load(handle))

        # fix the maskID field
        for path, info in dataset_dict['Images'].items():
            fixed_mask_id = {}
            for key, value in info['MaskID'].items():
                fixed_mask_id[int(key)] = value
            dataset_dict['Images'][path]['MaskID'] = fixed_mask_id

        # The dataset dictionary is organized as follows:
        # {
        #   "Classes": {
        #       "__background__" : 0
        #       "class_name" : 1
        #       ...
        #   }
        #   "Images": {
        #       "image_1_filename": {
        #           "Annotations":"path_to_annotation_1.xml"
        #           "MaskPath":"path_to_mask_1.png"
        #           "MaskID":{
        #               id_0:"class_name"
        #               ...
        #           }
        #       ...
        #   }
        #
        # Annotations = bounding boxes of object instances in the image
        # MaskID = correspondences between mask colors and class label

        # Add classes (except __background__, that is added by default)
        # We need to make sure that the classes are added according to the order of their IDs in the dataset
        # Or the names will be screwed up
        class_entries_sorted_by_id = sorted(dataset_dict['Classes'].items(), key=lambda kv: kv[1])

        # for class_name, id in dataset_dict['Classes'].items():
        #     if class_name=='__background__':
        #         continue
        #     self.add_class("tabletop", id, class_name)

        for label, id in class_entries_sorted_by_id:
            if label == '__background__':
                continue
            self.add_class('tabletop', id, label)

        # Iterate over images in the dataset to add them
        for path, info in dataset_dict['Images'].items():
            image_path = os.path.join(subset_dir, path)

            #TODO: verify if actually image size is useful when loading the masks
            image = skimage.io.imread(image_path)
            height, width = image.shape[:2]

            self.add_image(
                "tabletop",
                image_id = image_path,
                path = image_path,
                width = width, height = height,
                mask_path = os.path.join(subset_dir, info['MaskPath']),
                mask_ids = info['MaskID'])

    def get_class_id(self, image_text_label):
        """Return class id according to the image textual label
        Returns:
            class_id: int of the class id according to self.class_info. -1
                if class not found
        """
        for this_class in self.class_info:
            if this_class["name"] != image_text_label:
                continue
            else:
                return this_class["id"]

        return -1

    def load_mask(self, image_id):
        """Generate instance masks for an image.
        Returns:
            masks: A bool array of shape [height, width, instance count] with
                    one mask per instance.
            class_ids: a 1D array of class IDs of the instance masks.
        """
        # If not a tabletop dataset image, delegate to parent class.
        image_info = self.image_info[image_id]
        if image_info["source"] != "tabletop":
            return super(self.__class__, self).load_mask(image_id)

        mask_image = skimage.io.imread(image_info["mask_path"])
        mask_classes = image_info["mask_ids"]

        # Create empty return values
        masks = np.zeros( (image_info["height"], image_info["width"], len(mask_classes.keys())),
                            dtype=np.bool)
        class_ids = np.zeros(len(mask_classes.keys()), dtype=np.int32)

        # The dataset already contains binary maps, we just need to extract
        # them from the .png mask according to their ID
        # The ID in the mask file is different for each instance, therefore
        # we need to refer to the text label and find out the ID in
        # self.class_info
        current_inst = 0
        for instance_id, instance_class_label in mask_classes.items():
            this_instance_id = self.get_class_id(instance_class_label)
            # enforce ids to be positive!
            assert this_instance_id > 0
            masks[:, :, current_inst] = mask_image == instance_id
            class_ids[current_inst] = this_instance_id
            current_inst += 1

        return masks, class_ids

    def image_reference(self, image_id):
        """Return the path of the image."""
        info = self.image_info[image_id]
        if info["source"] == "tabletop":
            return info["path"]
        else:
            super(self.__class__, self).image_reference(image_id)

def train(model):
    """Train the model."""

    # Training dataset
    dataset_train = TabletopDataset()
    dataset_train.load_tabletop(args.dataset, "train")
    dataset_train.prepare()

    # Validation dataset
    dataset_val = TabletopDataset()
    dataset_val.load_tabletop(args.dataset, "val")
    dataset_val.prepare()


    # *** This training schedule is an example. Update to your needs ***
    # Since we're using a very small dataset, and starting from
    # COCO trained weights, we don't need to train too long. Also,
    # no need to train all layers, just the heads should do it.
    print("Training network stages " + config.LAYERS_TUNE)
    model.train(dataset_train, dataset_val,
                learning_rate=config.LEARNING_RATE,
                epochs=config.EPOCHS,
                layers=config.LAYERS_TUNE)


def color_splash(image, mask):
    """Apply color splash effect.
    image: RGB image [height, width, 3]
    mask: instance segmentation mask [height, width, instance count]

    Returns result image.
    """
    # Make a grayscale copy of the image. The grayscale copy still
    # has 3 RGB channels, though.
    gray = skimage.color.gray2rgb(skimage.color.rgb2gray(image)) * 255
    # Copy color pixels from the original color image where mask is set
    if mask.shape[-1] > 0:
        # We're treating all instances as one, so collapse the mask into one layer
        mask = (np.sum(mask, -1, keepdims=True) >= 1)
        splash = np.where(mask, image, gray).astype(np.uint8)
    else:
        splash = gray.astype(np.uint8)
    return splash


def detect_and_color_splash(model, image_path=None, video_path=None):
    assert image_path or video_path

    # Image or video?
    if image_path:
        # Run model detection and generate the color splash effect
        print("Running on {}".format(args.image))
        # Read image
        image = skimage.io.imread(args.image)
        # Detect objects
        r = model.detect([image], verbose=1)[0]
        # Color splash
        splash = color_splash(image, r['masks'])
        # Save output
        file_name = "splash_{:%Y%m%dT%H%M%S}.png".format(datetime.datetime.now())
        skimage.io.imsave(file_name, splash)
    elif video_path:
        import cv2
        # Video capture
        vcapture = cv2.VideoCapture(video_path)
        width = int(vcapture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(vcapture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = vcapture.get(cv2.CAP_PROP_FPS)

        # Define codec and create video writer
        file_name = "splash_{:%Y%m%dT%H%M%S}.avi".format(datetime.datetime.now())
        vwriter = cv2.VideoWriter(file_name,
                                  cv2.VideoWriter_fourcc(*'MJPG'),
                                  fps, (width, height))

        count = 0
        success = True
        while success:
            print("frame: ", count)
            # Read next image
            success, image = vcapture.read()
            if success:
                # OpenCV returns images as BGR, convert to RGB
                image = image[..., ::-1]
                # Detect objects
                r = model.detect([image], verbose=0)[0]
                # Color splash
                splash = color_splash(image, r['masks'])
                # RGB -> BGR to save image to video
                splash = splash[..., ::-1]
                # Add image to video writer
                vwriter.write(splash)
                count += 1
        vwriter.release()
    print("Saved to ", file_name)


############################################################
#  Training
############################################################

if __name__ == '__main__':
    import argparse

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Train Mask R-CNN to detect balloons.')
    parser.add_argument("command",
                        metavar="<command>",
                        help="'train' or 'splash'")
    parser.add_argument('--dataset', required=False,
                        metavar="/path/to/balloon/dataset/",
                        help='Directory of the Balloon dataset')
    parser.add_argument('--weights', required=True,
                        metavar="/path/to/weights.h5",
                        help="Path to weights .h5 file or 'coco'")
    parser.add_argument('--logs', required=False,
                        default=DEFAULT_LOGS_DIR,
                        metavar="/path/to/logs/",
                        help='Logs and checkpoints directory (default=logs/)')
    parser.add_argument('--image', required=False,
                        metavar="path or URL to image",
                        help='Image to apply the color splash effect on')
    parser.add_argument('--video', required=False,
                        metavar="path or URL to video",
                        help='Video to apply the color splash effect on')
    args = parser.parse_args()

    # Validate arguments
    if args.command == "train":
        assert args.dataset, "Argument --dataset is required for training"
    elif args.command == "splash":
        assert args.image or args.video,\
               "Provide --image or --video to apply color splash"

    print("Weights: ", args.weights)
    print("Dataset: ", args.dataset)
    print("Logs: ", args.logs)

    # Configurations
    if args.command == "train":
        config = TabletopConfig()
    else:
        class InferenceConfig(TabletopConfig):
            # Set batch size to 1 since we'll be running inference on
            # one image at a time. Batch size = GPU_COUNT * IMAGES_PER_GPU
            GPU_COUNT = 1
            IMAGES_PER_GPU = 1
        config = InferenceConfig()
    config.display()

    # Create model
    if args.command == "train":
        model = modellib.MaskRCNN(mode="training", config=config,
                                  model_dir=args.logs)
    else:
        model = modellib.MaskRCNN(mode="inference", config=config,
                                  model_dir=args.logs)

    # Select weights file to load
    if args.weights.lower() == "coco":
        weights_path = COCO_WEIGHTS_PATH
        # Download weights file
        if not os.path.exists(weights_path):
            utils.download_trained_weights(weights_path)
    elif args.weights.lower() == "last":
        # Find last trained weights
        weights_path = model.find_last()
    elif args.weights.lower() == "imagenet":
        # Start from ImageNet trained weights
        weights_path = model.get_imagenet_weights()
    else:
        weights_path = args.weights

    # Load weights
    print("Loading weights ", weights_path)
    if args.weights.lower() == "coco":
        # Exclude the last layers because they require a matching
        # number of classes
        model.load_weights(weights_path, by_name=True, exclude=[
            "mrcnn_class_logits", "mrcnn_bbox_fc",
            "mrcnn_bbox", "mrcnn_mask"])
    else:
        model.load_weights(weights_path, by_name=True)

    # Train or evaluate
    if args.command == "train":
        train(model)
    elif args.command == "splash":
        detect_and_color_splash(model, image_path=args.image,
                                video_path=args.video)
    else:
        print("'{}' is not recognized. "
              "Use 'train' or 'splash'".format(args.command))

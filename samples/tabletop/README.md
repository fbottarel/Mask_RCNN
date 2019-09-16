# YCB-Video training example

This directory presents tools to train, test and evaluate Mask R-CNN models on the YCB-Video dataset.

###Dataset

YCB-Video was proposed as part of the [PoseCNN](https://arxiv.org/abs/1711.00199) pose estimation framework. It features more than 200K images of 21 YCB objects in indoor environments annotated with detection bounding boxes, instance segmentation masks and object poses for each frame. You can find information about the dataset [at the project page](https://rse-lab.cs.washington.edu/projects/posecnn/).

In order to have this code work, all you need to do is to download the dataset itself, which is a pretty hefty package (~270 GB compressed). Once downloaded and uncompressed, store it somewhere convenient (for instance, a `dataset` directory in the root of the repo).

###Code

This example comes with a few different files:

tabletop.py - the main script. This contains code for training, evaluating and testing the model, as well as the training schedule

configurations.py - training and inference configuration details for the YCB-Video dataset       

datasets.py - classes inherited from the `utils.Dataset` class, tailored on YCB-Video (and another dataset class that I will document in the future)

demo.ipynb - jupyter notebook script to quickly evaluate a model prediction

inspect_dataset.ipynb - jupyter notebook to inspect sample dataset images

inspect_model.ipynb - to be added soon

inspect_weights.ipynb - to be added soon

mask_rcnn_tabletop.h5 - sample weights to test the installation

### Usage

Once you have installed the repo according to the main README file, run

```python tabletop.py --help```

and you shall be greeted with usage instructions!

```
usage: tabletop.py [-h] [--dataset /path/to/dataset/] --weights
                   /path/to/weights.h5 [--logs /path/to/logs/]
                   [--image path or URL to image]
                   [--video path or URL to video]
                   <command>

Train Mask R-CNN to detect objects.

positional arguments:
  <command>             'train', 'splash', 'evaluate'

optional arguments:
  -h, --help            show this help message and exit
  --dataset /path/to/dataset/
                        Directory of the dataset
  --weights /path/to/weights.h5
                        Path to weights .h5 file or 'coco'
  --logs /path/to/logs/
                        Logs and checkpoints directory (default=logs/)
  --image path or URL to image
                        Image to detect objects on
  --video path or URL to video
                        Video to detect objects on
```

Suppose the root directory of your local copy of YCB-Video is located in path  `[ROOT_YCBVIDEO]` and you have trained model weights at path `[TRAINED_MODEL.h5]`

You can fine-tune from a pretrained model (on COCO):
```
python tabletop.py --dataset [ROOT_YCBVIDEO] --weights coco train
```
or, if you have a trained model (like the one we provide) that you want to start from:

```
python tabletop.py --dataset [ROOT_YCBVIDEO] --weights [TRAINED_MODEL.h5] train
```
You can splash detection results on an image or video by running

```
python tabletop.py --dataset [ROOT_YCBVIDEO] --weights [TRAINED_MODEL.h5] --image [IMAGE_PATH] splash
```
```
python tabletop.py --dataset [ROOT_YCBVIDEO] --weights [TRAINED_MODEL.h5] --video [VIDEO_PATH] splash
```

You can also evaluate your model according to the COCO mAP metrics with

```
python tabletop.py --dataset [ROOT_YCBVIDEO] --weights [TRAINED_MODEL.h5] evaluate
```

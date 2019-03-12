"""
YARP module to test the trained Mask R-CNN model online with live camera data.

Refer to the README.md of the repo for the setup of the requirements of the model. Also, refer to the YARP documentation
 in order to install YARP Python bindings (http://www.yarp.it/yarp_swig.html)

Author: Fabrizio Bottarel (fabrizio.bottarel@iit.it)
"""

import os
import sys
import argparse
import json
import datetime
import numpy as np
import skimage.draw
import matplotlib
import matplotlib.pyplot as plt
from PIL import Image
import skimage

#   Root directory of the project
ROOT_DIR = os.path.abspath("../../")

#   Import Mask R-CNN
sys.path.append(ROOT_DIR)
from mrcnn import utils
import mrcnn.model as modellib
from mrcnn import visualize

#   Import the tabletop dataset custom configuration
import tabletop

#   Declare directories for weights and logs
MODEL_DIR = os.path.join(ROOT_DIR, "logs")

#   Import YARP bindings
YARP_BUILD_DIR = "/home/fbottarel/robot-code/yarp/build"
YARP_BINDINGS_DIR = os.path.join(YARP_BUILD_DIR, "lib/python")

if YARP_BINDINGS_DIR not in sys.path:
    sys.path.insert(0, YARP_BINDINGS_DIR)

import yarp
yarp.Network.init()

#   Add environment variables depending on the system
os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

class MaskRCNNWrapperModule (yarp.RFModule):

    def __init__(self, args):
        '''
        Initialize the module with None everywhere.
        The configure() method will be used to set everything up
        '''

        yarp.RFModule.__init__(self)

        self.__rf = None

        self._input_buf_image = None
        self._input_buf_array = None

        self._output_buf_image = None
        self._output_buf_array = None

        self._port_out = None
        self._port_in = None

        self._module_name = args.module_name

        self._input_img_width = args.input_img_width
        self._input_img_height = args.input_img_height

        self._model_weights_path = os.path.join(MODEL_DIR, args.model_weights_path)

        self._model = None

        self._class_colors = None

    def configure (self, rf):
        '''
        Configure the module internal variables and ports according to resource finder
        '''

        self._rf = rf

        #   Input
        #   Image port initialization

        self._port_in = yarp.BufferedPortImageRgb()
        self._port_in.open('/' +  self._module_name + '/RGBimage:i')

        #   Input buffer initialization

        self._input_buf_image = yarp.ImageRgb()
        self._input_buf_image.resize(self._input_img_width, self._input_img_height)
        #self._input_buf_array = Image.new(mode='RGB', size=(self._input_img_width, self._input_img_height))
        self._input_buf_array = np.ones((self._input_img_height, self._input_img_width, 3), dtype = np.uint8)
        self._input_buf_image.setExternal(self._input_buf_array,
                                          self._input_buf_array.shape[1],
                                          self._input_buf_array.shape[0])

        print('Input image buffer configured')

        #   Output
        #   Output image port initialization

        self._port_out = yarp.Port()
        self._port_out.open('/' + self._module_name + '/outPort:o')

        #   Output buffer initialization
        self._output_buf_image = yarp.ImageRgb()
        self._output_buf_image.resize(self._input_img_width, self._input_img_height)
        #self._output_buf_array = Image.new(mode='RGB', size=(self._input_img_width, self._input_img_height))
        self._output_buf_array = np.zeros((self._input_img_height, self._input_img_width, 1), dtype = np.float32)
        self._output_buf_image.setExternal(self._output_buf_array,
                                           self._output_buf_array.shape[1],
                                           self._output_buf_array.shape[0])

        print('Output image buffer configured')

        #   Inference model setup
        #   Configure some parameters for inference
        config = tabletop.YCBVideoConfigInference()
        config.display()

        self._model = modellib.MaskRCNN(mode='inference',
                                  model_dir=MODEL_DIR,
                                  config=config)

        print('Inference model configured')

        #   Load class names
        self._dataset = tabletop.YCBVideoDataset()
        #self._dataset.load_dataset(os.path.join(ROOT_DIR, "datasets", "YCB_Video_Dataset"), 'train')
        #self._dataset.prepare()
        #self._class_names = self._dataset.class_names

		# Add the classes (order is vital for mask id consistency)		
        self._class_names = ['__background__'] + self._dataset.parse_class_list(os.path.join(ROOT_DIR, "datasets", "YCB_Video_Dataset"))

        print("Class names: ", self._class_names)

        #   Load model weights
        try:
            assert os.path.exists(self._model_weights_path)
        except AssertionError as error:
            print("Model weights path invalid: file does not exist")
            print(error)
            return False

        self._model.load_weights(self._model_weights_path, by_name=True)

        print("Model weights loaded")

        #   Visualization setup
        self._class_colors = {}
        random_class_colors = visualize.random_colors(len(self._class_names))
        self._class_colors = {class_id:color for (color, class_id) in zip(random_class_colors, self._class_names)}

        self._figure, self._ax = plt.subplots(1)
        plt.ion()

        return True

    def interruptModule(self):

        self._port_in.interrupt()
        self._port_out.interrupt()

        return True

    def close(self):

        self._port_in.close()
        self._port_out.close()

        return True

    def getPeriod(self):

        return 0.0

    def updateModule(self):
        '''
        During module update, acquire a streamed image, perform inference using the model and then
        return/display results
        '''

        input_img = self._port_in.read()
        if input_img is None:
            print('Invalid input image (image is None)')
        else:
            self._input_buf_image.copy(input_img)
            assert self._input_buf_array.__array_interface__['data'][0] == self._input_buf_image.getRawImage().__int__()

            tmp = np.ascontiguousarray(self._input_buf_array[:, :, :])
            self._output_buf_array = tmp.astype(np.float32)

            self._port_out.write(self._output_buf_image)
            # self._port_out.write(input_img)

            frame = self._input_buf_array

            #   run detection/segmentation on frame
            #   display/return results
            results = self._model.detect([frame], verbose=1)

            # Visualize results
            r = results[0]

            plt.cla()
            
            instance_colors = []
            print('Instances detected: ', r['class_ids'])
            instance_colors = [self._class_colors[self._class_names[class_id]] for class_id in r['class_ids']]
            visualize.display_instances(frame, r['rois'], r['masks'], r['class_ids'],
                                       self._class_names, r['scores'], ax=self._ax, colors=instance_colors)

            plt.pause(0.01)

        return True

def parse_args():
    '''
    Parser for command line input arguments
    :return: input arguments
    '''

    parser = argparse.ArgumentParser(description='Mask R-CNN live demo')

    parser.add_argument('--name', dest='module_name', help='YARP module name',
                        default='instanceSegmenter', type=str)
    parser.add_argument('--width', dest='input_img_width', help='Input image width',
                        default=640, type=int)
    parser.add_argument('--height', dest='input_img_height', help='Input image height',
                        default=480, type=int)

    parser.add_argument(dest='model_weights_path', help='Model weights path relative to the directory PROJECT_ROOT/logs',
			type=str)

    return parser.parse_args()

if __name__ == '__main__':

    #   Parse arguments
    args = parse_args()

    yarp.Network.init()

    detector = MaskRCNNWrapperModule(args)

    rf = yarp.ResourceFinder()
    rf.setVerbose(True)
    rf.setDefault('name', 'instanceSegmenter')

    rf.configure(sys.argv)

    print('Configuration complete')
    detector.runModule(rf)

    plt.ioff()
    plt.show()


# Copyright Niantic 2019. Patent Pending. All rights reserved.
#
# This software is licensed under the terms of the Monodepth2 licence
# which allows for non-commercial use only, the full terms of which are made
# available in the LICENSE file.

from __future__ import absolute_import, division, print_function

import os
import sys
import glob
import argparse
import numpy as np
import PIL.Image as pil
import matplotlib as mpl
import matplotlib.cm as cm

import torch
from torchvision import transforms, datasets

import networks
from layers import disp_to_depth
from utils import download_model_if_doesnt_exist, readlines
from evaluate_depth import STEREO_SCALE_FACTOR

test_files_dir = '/home/radice/neuralNetworks/monodepth2/splits'
kitti_path = '/home/radice/neuralNetworks/results/monodepth2/KITTI/'
oxford_path = '/home/radice/neuralNetworks/results/monodepth2/OXFORD/'


def parse_args():
    parser = argparse.ArgumentParser(
        description='Simple testing funtion for Monodepthv2 models.')

    parser.add_argument('--image_path', type=str,
                        help='path to a test image or folder of images', required=True)
    parser.add_argument('--model_name', type=str,
                        help='name of a pretrained model to use',
                        choices=[
                            "mono_640x192",
                            "stereo_640x192",
                            "mono+stereo_640x192",
                            "mono_no_pt_640x192",
                            "stereo_no_pt_640x192",
                            "mono+stereo_no_pt_640x192",
                            "mono_1024x320",
                            "stereo_1024x320",
                            "mono+stereo_1024x320",
                            "oxford_stereo_640x192",
                            "oxford_mono_640x192",
                            "oxford"])
    parser.add_argument('--ext', type=str,
                        help='image extension to search for in folder', default="jpg")
    parser.add_argument("--no_cuda",
                        help='if set, disables CUDA',
                        action='store_true')
    parser.add_argument("--pred_metric_depth",
                        help='if set, predicts metric depth instead of disparity. (This only '
                             'makes sense for stereo-trained KITTI models).',
                        action='store_true')
    # aggiunti da me
    parser.add_argument("--dataset",
                        help='dataset to select for metric prediction',
                        choices=['KITTI', 'OXFORD'],
                        required=True)
    parser.add_argument("--model",
                        help='name of the model used, needed to correctly order the test images in folders'
                             'esempio: 2021-10-25-mono-oxford-alternativeroute-crop-mixedsplit',
                        required=True)
    parser.add_argument("--dataset_run",
                        help='name of the run used, needed to correctly order the test images in folders.'
                             'esempio: 2014-06-26-09-31-18',
                        required=True)
    parser.add_argument("--use_test_set",
                        help='choice of using the test set .txt file in monodepth2/splits',
                        action="store_true")
    parser.add_argument("--crop_area",
                        help='area of the cropped image in Oxford', required=False, default=(0, 240, 1280, 720))
    parser.add_argument("--resnet",
                        type=int,
                        default=18)
    return parser.parse_args()


def test_simple(args):
    """Function to predict for a single image or folder of images
    """
    assert args.model_name is not None, \
        "You must specify the --model_name parameter; see README.md for an example"

    if torch.cuda.is_available() and not args.no_cuda:
        device = torch.device("cuda")
    else:
        device = torch.device("cpu")

    if args.pred_metric_depth and "stereo" not in args.model_name:
        print("Warning: The --pred_metric_depth flag only makes sense for stereo-trained KITTI "
              "models. For mono-trained models, output depths will not in metric space.")

    download_model_if_doesnt_exist(args.model_name)
    model_path = os.path.join("models", args.model_name)
    print("-> Loading model from ", model_path)
    encoder_path = os.path.join(model_path, "encoder.pth")
    depth_decoder_path = os.path.join(model_path, "depth.pth")

    # LOADING PRETRAINED MODEL
    print("   Loading pretrained encoder")
    if args.resnet == 18:
        encoder = networks.ResnetEncoder(18, False)
    elif args.resnet == 50:
        encoder = networks.ResnetEncoder(50, False)
    else:
        raise Exception('Can not find resnet {}'.format(args.resnet))

    loaded_dict_enc = torch.load(encoder_path, map_location=device)

    # extract the height and width of image that this model was trained with
    feed_height = loaded_dict_enc['height']
    feed_width = loaded_dict_enc['width']
    filtered_dict_enc = {k: v for k, v in loaded_dict_enc.items() if k in encoder.state_dict()}
    encoder.load_state_dict(filtered_dict_enc)
    encoder.to(device)
    encoder.eval()

    print("   Loading pretrained decoder")
    depth_decoder = networks.DepthDecoder(
        num_ch_enc=encoder.num_ch_enc, scales=range(4))

    loaded_dict = torch.load(depth_decoder_path, map_location=device)
    depth_decoder.load_state_dict(loaded_dict)

    depth_decoder.to(device)
    depth_decoder.eval()

    folder = args.model
    run = args.dataset_run

    if args.dataset == 'KITTI':
        output_directory = os.path.join(kitti_path, folder, run)
        if not os.path.isdir(output_directory):
            os.makedirs(output_directory)

    if args.dataset == 'OXFORD':
        output_directory = os.path.join(oxford_path, folder, run)
        if not os.path.isdir(output_directory):
            os.makedirs(output_directory)

    # FINDING INPUT IMAGES
    if os.path.isfile(args.image_path):
        # Only testing on a single image
        paths = [args.image_path]
        # # KITTI path finder
        # if args.dataset == 'KITTI':
        #     print('-> USING KITTI TEST IMAGE')
        #     splitted = paths[0].split('/')
        #     folder = [s for s in splitted if "_sync" in s][0]
        # # OXFORD path finder
        # if args.dataset == 'OXFORD':
        #     print('-> USING OXFORD TEST IMAGE')
        #     splitted = paths[0].split('/')
        #     folder = [s for s in splitted if ('2014' or '2015') in s][0]
    elif os.path.isdir(args.image_path):
        paths = []
        # KITTI path finder
        if args.dataset == 'KITTI':
            # Searching folder for images
            if args.use_test_set:
                side_map = {"2": 2, "3": 3, "l": 2, "r": 3}
                # open test_files.txt
                test_file_path = os.path.join(test_files_dir, 'eigen', 'test_files.txt')
                train_filenames = readlines(test_file_path)
                for file in train_filenames:
                    splitted = file.split(' ')
                    paths.append(os.path.join(splitted[0], side_map[splitted[2]], "{}{}".format(splitted[1], '.jpg')))
        # OXFORD path finder
        if args.dataset == 'OXFORD':
            # Searching folder for images
            if args.use_test_set:
                side_map = {"l": "left", "r": "right"}
                # open test_files.txt
                test_file_path = os.path.join(test_files_dir, 'oxford', 'test_files.txt')
                train_filenames = readlines(test_file_path)
                for file in train_filenames:
                    splitted = file.split(' ')
                    paths.append(os.path.join(splitted[0], side_map[splitted[2]], "{}{}".format(splitted[1], '.jpg')))
    else:
        raise Exception("Can not find args.image_path: {}".format(args.image_path))

    print("-> Predicting on {:d} test images".format(len(paths)))

    # PREDICTING ON EACH IMAGE IN TURN
    with torch.no_grad():
        for idx, image_path in enumerate(paths):

            if image_path.endswith("_disp.jpg"):
                # don't try to predict disparity for a disparity image!
                continue

            # Load image and preprocess
            input_image = pil.open(image_path).convert('RGB')

            # effettuo il crop dell'immagine se il dataset è OXFORD
            if args.dataset == 'OXFORD':
                crop_area = tuple(args.crop_area)
                input_image = input_image.crop(crop_area)

            original_width, original_height = input_image.size
            input_image = input_image.resize((feed_width, feed_height), pil.LANCZOS)
            input_image = transforms.ToTensor()(input_image).unsqueeze(0)

            # PREDICTION
            input_image = input_image.to(device)
            features = encoder(input_image)
            outputs = depth_decoder(features)

            disp = outputs[("disp", 0)]
            disp_resized = torch.nn.functional.interpolate(
                disp, (original_height, original_width), mode="bilinear", align_corners=False)

            # Saving numpy file
            output_name = os.path.splitext(os.path.basename(image_path))[0]
            scaled_disp, depth = disp_to_depth(disp, 0.1, 100)
            if args.pred_metric_depth:
                #name_dest_npy = os.path.join(output_directory, "{}_depth.npy".format(folder + '_' + output_name))
                name_dest_npy = os.path.join(output_directory, "{}_depth.npy".format(output_name))
                if args.dataset == 'KITTI':
                    print('-> KITTI STEREO_SCALE_FACTOR', STEREO_SCALE_FACTOR)
                    metric_depth = STEREO_SCALE_FACTOR * depth.cpu().numpy()
                if args.dataset == 'OXFORD':
                    # oxford baseline between left and right cameras
                    oxford_baseline = 0.24
                    stereo_scale_factor = oxford_baseline / 0.1
                    metric_depth = stereo_scale_factor * depth.cpu().numpy()
                    print('-> OXFORD STEREO_SCALE_FACTOR', stereo_scale_factor)
                np.save(name_dest_npy, metric_depth)
            else:
                #name_dest_npy = os.path.join(output_directory, "{}_disp.npy".format(folder +'_' + output_name))
                name_dest_npy = os.path.join(output_directory, "{}_disp.npy".format(output_name))
                np.save(name_dest_npy, scaled_disp.cpu().numpy())

            # Saving colormapped depth image
            disp_resized_np = disp_resized.squeeze().cpu().numpy()
            vmax = np.percentile(disp_resized_np, 95)
            normalizer = mpl.colors.Normalize(vmin=disp_resized_np.min(), vmax=vmax)
            mapper = cm.ScalarMappable(norm=normalizer, cmap='magma')
            colormapped_im = (mapper.to_rgba(disp_resized_np)[:, :, :3] * 255).astype(np.uint8)
            im = pil.fromarray(colormapped_im)

            #name_dest_im = os.path.join(output_directory, "{}_disp.jpeg".format(folder + '_' + output_name))
            name_dest_im = os.path.join(output_directory, "{}_disp.jpeg".format(output_name))
            im.save(name_dest_im)

            print("   Processed {:d} of {:d} images - saved predictions to:".format(
                idx + 1, len(paths)))
            print("   - {}".format(name_dest_im))
            print("   - {}".format(name_dest_npy))

    print('-> Done!')


if __name__ == '__main__':
    args = parse_args()
    test_simple(args)

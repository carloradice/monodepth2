from __future__ import absolute_import, division, print_function

import os
import numpy as np
import PIL.Image as pil
from .mono_dataset import MonoDataset
import sys

class OXFORDDataset(MonoDataset):
    """
    Super class for different types of OXFORD dataset loaders
    """
    def __init__(self, *args, **kwargs):
        super(OXFORDDataset, self).__init__(*args, **kwargs)

        # NOTE: Make sure your intrinsics matrix is *normalized* by the original image size.
        # To normalize you need to scale the first row by 1 / image_width and the second row
        # by 1 / image_height. Monodepth2 assumes a principal point to be exactly centered.
        # If your principal point is far from the center you might need to disable the horizontal
        # flip augmentation.

        # Monodepth2 assumes a principal point to be exactly centered
        # stereo wide
        # intrinsics:  983.044006,  983.044006, 643.646973, 493.378998
        # se croppo fx e fy rimangono gli stessi
        # vengono modificati cx e cy secondo questo
        # https://github.com/BerkeleyAutomation/perception/blob/6b7bfadae206b130dce21b63034d70211ba7a9f8/perception/camera_intrinsics.py#L184
        width = 1280
        height = 960
        fx = 983.044006
        fx /= width
        fy = 983.044006
        fy /= height
        cx = 643.646973
        cy = 493.378998
        # Parameters
        # ----------
        # crop_height : int
        #     height of crop window
        # crop_width : int
        #     width of crop window
        # crop_ci : int
        #     row of crop window center
        # crop_cj : int
        #     col of crop window center
        self.crop_area = (0, 300, 1280, 760)
        crop_width = self.crop_area[2] - self.crop_area[0]
        crop_height = self.crop_area[3] - self.crop_area[1]
        crop_ci = self.crop_area[3] - (crop_height / 2)
        crop_cj = self.crop_area[2] - (crop_width / 2)
        crop_cx = cx + float(crop_width-1)/2 - crop_cj
        crop_cy = cy + float(crop_height-1)/2 - crop_ci
        crop_cx /= width
        crop_cy /= height

        self.K = np.array([[fx, 0, crop_cx, 0],
                           [0, fy, crop_cy, 0],
                           [0, 0, 1, 0],
                           [0, 0, 0, 1]], dtype=np.float32)

        self.side_map = {"l": "left", "r": "right"}

        print('width:', width)
        print('height:', height)
        print('fx:', fx)
        print('fy:', fy)
        print('crop_width:', crop_width)
        print('crop_height:', crop_height)
        print('crop_cx:', crop_cx)
        print('crop_cy:', crop_cy, '\n')


    def check_depth(self):
        """
        Training without ground truth density maps
        """
        return False


    def get_color(self, folder, frame_index, side, do_flip):
        """
        Horizontal flip augmentation.
        """
        color = self.loader(self.get_image_path(folder, frame_index, side))

        if self.transform is not None:
            color = self.transform(color, self.crop_area)
            #color = self.transform(color)

        # If your principal point is far from the center you might need to disable the horizontal
        # flip augmentation.
        # if do_flip:
        #     color = color.transpose(pil.FLIP_LEFT_RIGHT)

        return color


class OXFORDRAWDataset(OXFORDDataset):
    """
    Oxford dataset
    """
    def __init__(self, *args, **kwargs):
        super(OXFORDRAWDataset, self).__init__(*args, **kwargs)

    def get_image_path(self, folder, frame_index, side):
        """
        TO DO
        """
        # frame_index è l'intero nome dell'immagine
        f_str = "{}{}".format(frame_index, self.img_ext)
        # folder contiene già il percorso completo fino alla cartella dell'immagine
        image_path = os.path.join(folder, "{}".format(self.side_map[side]), f_str)
        return image_path

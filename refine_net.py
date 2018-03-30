import torch
import torch.nn as nn
import torch.nn.functional as F

from vox_resnet import VoxResNet


class NonLocalBlock(nn.Module):
    def __init__(self, in_channels):
        super(NonLocalBlock, self).__init__()
        self.theta = nn.Conv3d(in_channels, in_channels/2, kernel_size=1)
        self.phi = nn.Conv3d(in_channels, in_channels/2, kernel_size=1)
        self.g = nn.Conv3d(in_channels, in_channels/2, kernel_size=1)
        self.h = nn.Conv3d(in_channels/2, in_channels, kernel_size=1)

class RefineNet(VoxResNet):
    def __init__(self, in_channels, num_classes, dropout=False):
        super(RefineNet, self).__init__(in_channels, num_classes, ftrlen=[32,64,128,256]) # different from paper and father
        self.dropout = dropout
        ftr_size = 128  # for refine, here

        # adaptive
        self.adaptive1 = nn.Conv3d(32, ftr_size, kernel_size=1) # in_channels == ftrlen list
        self.adaptive2 = nn.Conv3d(64, ftr_size, kernel_size=1)
        self.adaptive3 = nn.Conv3d(128, ftr_size, kernel_size=1)
        self.adaptive4 = nn.Conv3d(256, ftr_size, kernel_size=1)

        # dropout
        if self.dropout:
            self.dropout1 = nn.Dropout3d()
            self.dropout2 = nn.Dropout3d()
            self.dropout3 = nn.Dropout3d()
            self.dropout4 = nn.Dropout3d()

        # output conv
        self.smooth1 = nn.Conv3d(ftr_size, ftr_size, kernel_size=3, padding=1)
        self.smooth2 = nn.Conv3d(ftr_size, ftr_size, kernel_size=3, padding=1)
        self.smooth3 = nn.Conv3d(ftr_size, ftr_size, kernel_size=3, padding=1)
        self.smooth4 = nn.Conv3d(ftr_size, ftr_size, kernel_size=3, padding=1)

        self.predict = nn.Conv3d(ftr_size, num_classes, kernel_size=1, bias=True)

        self.non_local = NonLocalBlock(256)

    def upsample_3d(self, x, scale_factor):
        n, c, d, h, w = x.size()
        dst_h, dst_w = h*scale_factor, w*scale_factor
        x = x.view(n, c*d, h, w) # now support 3/4/5-D input
        x = F.upsample(x, size=(dst_h, dst_w), mode='bilinear')
        x = x.view(n, c, d, dst_h, dst_w)
        return x

    def forward(self, x):
        h1 = self.foward_stage1(x)
        h2 = self.foward_stage2(h1)
        h3 = self.foward_stage3(h2)
        h4 = self.foward_stage4(h3)
        #h4 = self.non_local(h4)

        h1 = self.adaptive1(F.relu(h1, inplace=False))
        h2 = self.adaptive2(F.relu(h2, inplace=False))
        h3 = self.adaptive3(F.relu(h3, inplace=False))
        h4 = self.adaptive4(F.relu(h4, inplace=False))

        if self.dropout:
            h1 = self.dropout1(h1)
            h2 = self.dropout2(h2)
            h3 = self.dropout3(h3)
            h4 = self.dropout4(h4)  # ??

        p4 = h4
        p3 = self.upsample_3d(p4, 2) + h3 # dimension matched because VoxResNet conv stride of 2?
        p3 = self.smooth3(p3)
        p2 = self.upsample_3d(p3, 2) + h2
        p2 = self.smooth2(p2)
        p1 = self.upsample_3d(p2, 2) + h1
        p1 = self.smooth1(p1)
        '''
        p4 = self.upsample_3d(h4, 8)
        p3 = self.upsample_3d(h3, 4)
        p2 = self.upsample_3d(h2, 2)
        p1 = torch.cat([h1,p2,p3,p4], dim=1)
        '''

        c = self.predict(p1)
        return c
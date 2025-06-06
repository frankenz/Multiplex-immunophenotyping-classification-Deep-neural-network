""" Utility functions for processing point clouds.

Author: Charles R. Qi, Hao Su
Date: November 2016
"""

import os
import sys
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

# Draw point cloud
from eulerangles import euler2mat

# Point cloud IO
import numpy as np
from plyfile import PlyData, PlyElement

 
# ----------------------------------------
# Point Cloud/Volume Conversions
# ----------------------------------------

def point_cloud_to_volume_batch(point_clouds, vsize=12, radius=1.0, flatten=True):
    """ Input is BxNx3 batch of point cloud
        Output is Bx(vsize^3)
    """
    vol_list = []
    for b in range(point_clouds.shape[0]):
        vol = point_cloud_to_volume(np.squeeze(point_clouds[b,:,:]), vsize, radius)
        if flatten:
            vol_list.append(vol.flatten())
        else:
            vol_list.append(np.expand_dims(np.expand_dims(vol, -1), 0))
    if flatten:
        return np.vstack(vol_list)
    else:
        return np.concatenate(vol_list, 0)


def point_cloud_to_volume(points, vsize, radius=1.0):
    """ input is Nx3 points.
        output is vsize*vsize*vsize
        assumes points are in range [-radius, radius]
    """
    vol = np.zeros((vsize,vsize,vsize))
    voxel = 2*radius/float(vsize)
    locations = (points + radius)/voxel
    locations = locations.astype(int)
    vol[locations[:,0],locations[:,1],locations[:,2]] = 1.0
    return vol

#a = np.zeros((16,1024,3))
#print point_cloud_to_volume_batch(a, 12, 1.0, False).shape

def volume_to_point_cloud(vol):
    """ vol is occupancy grid (value = 0 or 1) of size vsize*vsize*vsize
        return Nx3 numpy array.
    """
    vsize = vol.shape[0]
    assert(vol.shape[1] == vsize and vol.shape[1] == vsize)
    points = []
    for a in range(vsize):
        for b in range(vsize):
            for c in range(vsize):
                if vol[a,b,c] == 1:
                    points.append(np.array([a,b,c]))
    if len(points) == 0:
        return np.zeros((0,3))
    points = np.vstack(points)
    return points

def point_cloud_to_volume_v2_batch(point_clouds, vsize=12, radius=1.0, num_sample=128):
    """ Input is BxNx3 a batch of point cloud
        Output is BxVxVxVxnum_samplex3
        Added on Feb 19
    """
    vol_list = []
    for b in range(point_clouds.shape[0]):
        vol = point_cloud_to_volume_v2(point_clouds[b,:,:], vsize, radius, num_sample)
        vol_list.append(np.expand_dims(vol, 0))
    return np.concatenate(vol_list, 0)

def point_cloud_to_volume_v2(points, vsize, radius=1.0, num_sample=128):
    """ input is Nx3 points
        output is vsize*vsize*vsize*num_sample*3
        assumes points are in range [-radius, radius]
        samples num_sample points in each voxel, if there are less than
        num_sample points, replicate the points
        Added on Feb 19
    """
    vol = np.zeros((vsize,vsize,vsize,num_sample,3))
    voxel = 2*radius/float(vsize)
    locations = (points + radius)/voxel
    locations = locations.astype(int)
    loc2pc = {}
    for n in range(points.shape[0]):
        loc = tuple(locations[n,:])
        if loc not in loc2pc:
            loc2pc[loc] = []
        loc2pc[loc].append(points[n,:])
    #print loc2pc

    for i in range(vsize):
        for j in range(vsize):
            for k in range(vsize):
                if (i,j,k) not in loc2pc:
                    vol[i,j,k,:,:] = np.zeros((num_sample,3))
                else:
                    pc = loc2pc[(i,j,k)] # a list of (3,) arrays
                    pc = np.vstack(pc) # kx3
                    # Sample/pad to num_sample points
                    if pc.shape[0]>num_sample:
                        choices = np.random.choice(pc.shape[0], num_sample, replace=False)
                        pc = pc[choices,:]
                    elif pc.shape[0]<num_sample:
                        pc = np.lib.pad(pc, ((0,num_sample-pc.shape[0]),(0,0)), 'edge')
                    # Normalize
                    pc_center = (np.array([i,j,k])+0.5)*voxel - radius
                    #print 'pc center: ', pc_center
                    pc = (pc - pc_center) / voxel # shift and scale
                    vol[i,j,k,:,:] = pc 
                #print (i,j,k), vol[i,j,k,:,:]
    return vol

def point_cloud_to_image_batch(point_clouds, imgsize, radius=1.0, num_sample=128):
    """ Input is BxNx3 a batch of point cloud
        Output is BxIxIxnum_samplex3
        Added on Feb 19
    """
    img_list = []
    for b in range(point_clouds.shape[0]):
        img = point_cloud_to_image(point_clouds[b,:,:], imgsize, radius, num_sample)
        img_list.append(np.expand_dims(img, 0))
    return np.concatenate(img_list, 0)


def point_cloud_to_image(points, imgsize, radius=1.0, num_sample=128):
    """ input is Nx3 points
        output is imgsize*imgsize*num_sample*3
        assumes points are in range [-radius, radius]
        samples num_sample points in each pixel, if there are less than
        num_sample points, replicate the points
        Added on Feb 19
    """
    img = np.zeros((imgsize, imgsize, num_sample, 3))
    pixel = 2*radius/float(imgsize)
    locations = (points[:,0:2] + radius)/pixel # Nx2
    locations = locations.astype(int)
    loc2pc = {}
    for n in range(points.shape[0]):
        loc = tuple(locations[n,:])
        if loc not in loc2pc:
            loc2pc[loc] = []
        loc2pc[loc].append(points[n,:])
    for i in range(imgsize):
        for j in range(imgsize):
            if (i,j) not in loc2pc:
                img[i,j,:,:] = np.zeros((num_sample,3))
            else:
                pc = loc2pc[(i,j)]
                pc = np.vstack(pc)
                if pc.shape[0]>num_sample:
                    choices = np.random.choice(pc.shape[0], num_sample, replace=False)
                    pc = pc[choices,:]
                elif pc.shape[0]<num_sample:
                    pc = np.lib.pad(pc, ((0,num_sample-pc.shape[0]),(0,0)), 'edge')
                pc_center = (np.array([i,j])+0.5)*pixel - radius
                pc[:,0:2] = (pc[:,0:2] - pc_center)/pixel
                img[i,j,:,:] = pc
    return img
# ----------------------------------------
# Point cloud IO
# ----------------------------------------

def read_ply(filename):
    """ read XYZ point cloud from filename PLY file """
    plydata = PlyData.read(filename)
    pc = plydata['vertex'].data
    pc_array = np.array([[x, y, z] for x,y,z in pc])
    return pc_array


def write_ply(points, filename, text=True):
    """ input: Nx3, write points to filename as PLY format. """
    points = [(points[i,0], points[i,1], points[i,2]) for i in range(points.shape[0])]
    vertex = np.array(points, dtype=[('x', 'f4'), ('y', 'f4'),('z', 'f4')])
    el = PlyElement.describe(vertex, 'vertex', comments=['vertices'])
    PlyData([el], text=text).write(filename)


# ----------------------------------------
# Simple Point cloud and Volume Renderers
# ----------------------------------------

def draw_point_cloud(input_points, canvasSize=500, space=200, diameter=25,
                     xrot=0, yrot=0, zrot=0, switch_xyz=[0,1,2], normalize=True):
    """ Render point cloud to image with alpha channel.
        Input:
            points: Nx3 numpy array (+y is up direction)
        Output:
            gray image as numpy array of size canvasSizexcanvasSize
    """
    image = np.zeros((canvasSize, canvasSize))
    #print(input_points)
    #exit()
    if input_points is None or input_points.shape[0] == 0:
        return image

    points = input_points[:, switch_xyz]
    M = euler2mat(zrot, yrot, xrot)
    points = (np.dot(M, points.transpose())).transpose()

    # Normalize the point cloud
    # We normalize scale to fit points in a unit sphere
    if normalize:
        centroid = np.mean(points, axis=0)
        points -= centroid
        furthest_distance = np.max(np.sqrt(np.sum(abs(points)**2,axis=-1)))
        points /= furthest_distance

    # Pre-compute the Gaussian disk
    radius = (diameter-1)/2.0
    disk = np.zeros((diameter, diameter))
    for i in range(diameter):
        for j in range(diameter):
            if (i - radius) * (i-radius) + (j-radius) * (j-radius) <= radius * radius:
                disk[i, j] = np.exp((-(i-radius)**2 - (j-radius)**2)/(radius**2))
    mask = np.argwhere(disk > 0)
    dx = mask[:, 0]
    dy = mask[:, 1]
    dv = disk[disk > 0]
    
    # Order points by z-buffer
    zorder = np.argsort(points[:, 2])
    points = points[zorder, :]
    points[:, 2] = (points[:, 2] - np.min(points[:, 2])) / (np.max(points[:, 2] - np.min(points[:, 2])))
    max_depth = np.max(points[:, 2])
       
    for i in range(points.shape[0]):
        j = points.shape[0] - i - 1
        x = points[j, 0]
        y = points[j, 1]
        xc = canvasSize/2 + (x*space)
        yc = canvasSize/2 + (y*space)
        xc = int(np.round(xc))
        yc = int(np.round(yc))
        
        px = dx + xc
        py = dy + yc
        
        image[px, py] = image[px, py] * 0.7 + dv * (max_depth - points[j, 2]) * 0.3
    
    image = image / np.max(image)
    return image

def point_cloud_three_views(points):
    """ input points Nx3 numpy array (+y is up direction).
        return an numpy array gray image of size 500x1500. """ 
    # +y is up direction
    # xrot is azimuth
    # yrot is in-plane
    # zrot is elevation
    img1 = draw_point_cloud(points, zrot=110/180.0*np.pi, xrot=45/180.0*np.pi, yrot=0/180.0*np.pi)
    img2 = draw_point_cloud(points, zrot=70/180.0*np.pi, xrot=135/180.0*np.pi, yrot=0/180.0*np.pi)
    img3 = draw_point_cloud(points, zrot=180.0/180.0*np.pi, xrot=90/180.0*np.pi, yrot=0/180.0*np.pi)
    image_large = np.concatenate([img1, img2, img3], 1)
    return image_large


def point_cloud_three_views_demo():
    """ Demo for draw_point_cloud function """
    from PIL import Image
    points = read_ply('../third_party/mesh_sampling/piano.ply')
    im_array = point_cloud_three_views(points)
    img = Image.fromarray(np.uint8(im_array*255.0))
    img.save('piano.jpg')

if __name__=="__main__":
    point_cloud_three_views_demo()


def pyplot_draw_point_cloud(points, output_filename):
    """ points is a Nx3 numpy array """
    from mpl_toolkits.mplot3d import Axes3D
    import matplotlib
    matplotlib.use('Agg') 
    import matplotlib.pyplot as plt
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')
    ax.scatter(points[:,0], points[:,1], points[:,2], s=1)
    ax.set_xlabel('x')
    ax.set_ylabel('y')
    ax.set_zlabel('z')
    plt.savefig(output_filename)
    plt.close()
    
def pyplot_draw_point_cloud_nat_and_adv(points, points_adv, output_filename):
    """ points is a Nx3 numpy array """
    from mpl_toolkits.mplot3d import Axes3D
    import matplotlib
    matplotlib.use('Agg') 
    import matplotlib.pyplot as plt
    fig = plt.figure()
    xmax = np.max(points[:,0])
    x = points[:,0]
    x = np.extract(x>0,x)
    xmin = np.amin(x)
    #min_value = np.argmin(x)
    ymax = np.max(points[:,1])
    y = points[:,1]
    y = np.extract(y>0,y)
    ymin = np.amin(y)

    zmin, zmax = np.min(points[:,2])-0.1, np.max(points[:,2])+0.1
    #print (xmin, xmax, ymin, ymax,zmin, zmax)
    #exit()
    #df = pd.DataFrame(points[:,2])
    #colors = {'0':'red', '1':'green', '2':'blue', '3':'yellow','4':'red', '5':'green', '6':'blue','7':'blue'}
    #ax.scatter(df['population'], df['Area'], c=df['continent'].map(colors))
    #categories = np.array(points[:,2].astype(int))  # np.array([0, 2, 1, 1, 1, 2, 0, 0])
    #colormap = np.array(['r', 'g', 'b','r', 'g', 'b','r', 'g', 'b','r', 'g', 'b','r', 'g', 'b']) ### create 16 colors
    #df['key1'] = (4,4,4,6,6,6,8,8,8,8)
    #colors = np.where(df["key1"]==4,'r','-')
    #colors[df["key1"]==6] = 'g'
    #colors[df["key1"]==8] = 'b'

    ax = fig.add_subplot(111 , projection='3d')
    #fig, ax = plt.subplots(figsize=(50, 50))
    #ax.scatter(points[:,1], points[:,2], points[:,0], s=5, c=colormap[categories]) # c=points[:,2])
    #print (points,points[:,1], points[:,2], points[:,0])
    #exit()
    #s = [1 for n in range(len(points[:,1]))]
    #ax.scatter(x=points[:,1], y=points[:,0], s=1, c='b')
    ###ax.scatter(points[:,1], points[:,2], points[:,0], s=5, c='b')
    ax.set_xlabel('y')
    ax.set_ylabel('z')
    ax.set_zlabel('x')
    ax.set_xlim(ymin, ymax)
    ax.set_ylim(zmin, zmax)
    ax.set_zlim(xmin, xmax)
    #ax.set_xlabel('x')
    #ax.set_ylabel('y')
    #ax.set_zlabel('x')
    #ax.set_xlim(xmin, xmax)
    #ax.set_ylim(ymin, ymax)
    #ax.set_zlim(xmin, xmax)
    plt.axis('off')
    #plt.savefig(output_filename+'_1nat_x.jpg')
    plt.close()
    
    categoriesA = np.array(points_adv[:,2].astype(int))  # np.array([0, 2, 1, 1, 1, 2, 0, 0])
    categoriesBackA = np.array(points[:,2].astype(int)) 
    colormap = np.array(['w','#00FFFF', '#0000FF', '#FF4040','#B22222', '#A2CD5A', '#006400', 'w','w', '#8470FF', '#9A32CD','w', 'w', 'w','w', 'w', 'w']) ### create 16 colors
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')
    #print ('A  ',points_adv[:,1], points_adv[:,2], points_adv[:,0])
    #print ('A  ', points_adv[:,2])
    ax.scatter(points[:,0], points[:,1], s=20, c=colormap[categoriesBackA])
    ####ax.scatter(points_adv[:,1], points_adv[:,2], points_adv[:,0], s=110, c=colormap[categoriesA])  #c='r') cmap='viridis'
    ax.scatter(points_adv[:,0], points_adv[:,1], s=60, c=colormap[categoriesA])  #c='r') cmap='viridis'
    ax.set_xlabel('y')
    ax.set_ylabel('z')
    ax.set_zlabel('x')
    ax.set_xlim(ymin, ymax)
    ax.set_ylim(zmin, zmax)
    ax.set_zlim(xmin, xmax)
    plt.axis('off')
    plt.savefig(output_filename+'_2adv_x.jpg')
    #exit()
    plt.close()
    
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')
    #ax.scatter(points[:,2], points[:,0], points[:,1], s=5, c='b')
    ax.set_xlabel('z')
    ax.set_ylabel('x')
    ax.set_zlabel('y')
    ax.set_xlim(zmin, zmax)
    ax.set_ylim(xmin, xmax)
    ax.set_zlim(ymin, ymax)
    plt.axis('off')
    #plt.savefig(output_filename+'_3nat_y.jpg')
    plt.close()
    
    categoriesB = np.array(points_adv[:,2].astype(int))  # np.array([0, 2, 1, 1, 1, 2, 0, 0])
    categoriesBackB = np.array(points[:,2].astype(int))
    #colormap = np.array(['r', 'g', 'b','r', 'g', 'b','r', 'g', 'b','r', 'g', 'b','r', 'g', 'b']) ### create 16 colors
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')
    #print ('B  ',points_adv[:,2], points_adv[:,0], points_adv[:,1])
    ax.scatter(points[:,2], points[:,0], points[:,1], s=10, c=colormap[categoriesBackB])
    ax.scatter(points_adv[:,2], points_adv[:,0], points_adv[:,1], s=110, c=colormap[categoriesB])  #c='r') cmap='viridis'
    ax.set_xlabel('z')
    ax.set_ylabel('x')
    ax.set_zlabel('y')
    ax.set_xlim(zmin, zmax)
    ax.set_ylim(xmin, xmax)
    ax.set_zlim(ymin, ymax)
    plt.axis('off')
    plt.savefig(output_filename+'_4adv_y.jpg')
    plt.close()
    
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')
    #ax.scatter(points[:,0], points[:,1], points[:,2], s=5, c='b')
    ax.set_xlabel('x')
    ax.set_ylabel('y')
    ax.set_zlabel('z')
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_zlim(zmin, zmax)
    plt.axis('off')
    #plt.savefig(output_filename+'_5nat_z.jpg')
    plt.close()
    
    categoriesC = np.array(points_adv[:,2].astype(int))  # np.array([0, 2, 1, 1, 1, 2, 0, 0])
    categoriesBackC = np.array(points[:,2].astype(int))
    #colormap = np.array(['r', 'g', 'b','r', 'g', 'b','r', 'g', 'b','r', 'g', 'b','r', 'g', 'b']) ### create 16 colors
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')
    #print ('C  ',points_adv[:,0], points_adv[:,1], points_adv[:,2])
    ax.scatter(points[:,0], points[:,1], points[:,2], s=10, c=colormap[categoriesBackC])
    ax.scatter(points_adv[:,0], points_adv[:,1], points_adv[:,2], s=110, c=colormap[categoriesC]) #c='r')  cmap='viridis'
    ax.set_xlabel('x')
    ax.set_ylabel('y')
    ax.set_zlabel('z')
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_zlim(zmin, zmax)
    plt.axis('off')
    plt.savefig(output_filename+'_6adv_z.jpg')
    plt.close()

def plot_nat_interval_adv(points, drop_points, image_filename):
    from mpl_toolkits.mplot3d import Axes3D
    import matplotlib
    matplotlib.use('Agg') 
    import matplotlib.pyplot as plt
    xmin, xmax = np.min(points[:,0])-0.1, np.max(points[:,0])+0.1
    ymin, ymax = np.min(points[:,1])-0.1, np.max(points[:,1])+0.1
    zmin, zmax = np.min(points[:,2])-0.1, np.max(points[:,2])+0.1
    
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')
    ax.scatter(points[:,2], points[:,0], points[:,1], s=1, c='k')
    ax.scatter(drop_points[:,2], drop_points[:,0], drop_points[:,1], s=1, c='k')
    ax.set_xlabel('y')
    ax.set_ylabel('z')
    ax.set_zlabel('x')
    ax.set_xlim(zmin, zmax)
    ax.set_ylim(xmin, xmax)
    ax.set_zlim(ymin, ymax)
    plt.axis('off')
    plt.savefig(image_filename+'_y1.jpg', bbox_inches='tight')
    plt.close()

    #categoriesD = np.array(drop_points[:,0].astype(int))  # np.array([0, 2, 1, 1, 1, 2, 0, 0])
    #colormap = np.array(['r', 'g', 'b','r', 'g', 'b','r', 'g', 'b','r', 'g', 'b','r', 'g', 'b']) ### create 16 colors
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')
    ax.scatter(points[:,2], points[:,0], points[:,1], s=1, c='k')
    #print ('D  ',points_adv[:,2], points_adv[:,0], points_adv[:,1])
    ax.scatter(drop_points[:,2], drop_points[:,0], drop_points[:,1], s=25, c='r')
    ax.set_xlabel('y')
    ax.set_ylabel('z')
    ax.set_zlabel('x')
    ax.set_xlim(zmin, zmax)
    ax.set_ylim(xmin, xmax)
    ax.set_zlim(ymin, ymax)
    plt.axis('off')
    plt.savefig(image_filename+'_y2.jpg', bbox_inches='tight')
    plt.close()
    
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')
    ax.scatter(points[:,2], points[:,0], points[:,1], s=1, c='k')
    ax.set_xlabel('y')
    ax.set_ylabel('z')
    ax.set_zlabel('x')
    ax.set_xlim(zmin, zmax)
    ax.set_ylim(xmin, xmax)
    ax.set_zlim(ymin, ymax)
    plt.axis('off')
    plt.savefig(image_filename+'_y3.jpg', bbox_inches='tight')
    plt.close()

def pyplot_draw_volume(vol, output_filename):
    """ vol is of size vsize*vsize*vsize
        output an image to output_filename
    """
    points = volume_to_point_cloud(vol)
    pyplot_draw_point_cloud(points, output_filename)

def write_ply_color(points, labels, out_filename, num_classes=None):
    """ Color (N,3) points with labels (N) within range 0 ~ num_classes-1 as OBJ file """
    import matplotlib.pyplot as pyplot
    labels = labels.astype(int)
    N = points.shape[0]
    if num_classes is None:
        num_classes = np.max(labels)+1
    else:
        assert(num_classes>np.max(labels))
    fout = open(out_filename, 'w')
    #colors = [pyplot.cm.hsv(i/float(num_classes)) for i in range(num_classes)]
    colors = [pyplot.cm.jet(i/float(num_classes)) for i in range(num_classes)]
    for i in range(N):
        c = colors[labels[i]]
        c = [int(x*255) for x in c]
        fout.write('v %f %f %f %d %d %d\n' % (points[i,0],points[i,1],points[i,2],c[0],c[1],c[2]))
    fout.close()

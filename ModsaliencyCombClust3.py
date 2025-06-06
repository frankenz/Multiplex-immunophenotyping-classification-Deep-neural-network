import tensorflow as tf
import numpy as np
import argparse
import socket
import importlib
import time
import os
import scipy.misc
import sys
import setGPU
import math
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)
sys.path.append(os.path.join(BASE_DIR, 'models'))
sys.path.append(os.path.join(BASE_DIR, 'utils'))
import provider
import pc_util


parser = argparse.ArgumentParser()
parser.add_argument('--gpu', type=int, default=2, help='GPU to use [default: GPU 0]')
parser.add_argument('--model', default='pointnet_cls', help='Model name: pointnet_cls or pointnet_cls_basic [default: pointnet_cls]')
parser.add_argument('--batch_size', type=int, default=32, help='Batch Size during training [default: 1]')
parser.add_argument('--num_point', type=int, default=60, help='Point Number [256/512/1024/2048] [default: 1024]')
parser.add_argument('--model_path', default='log_box_60random5/model.ckpt', help='model checkpoint file path [default: log/model.ckpt]')
parser.add_argument('--dump_dir', default='dumplog_box_60random5', help='dump folder path [dump]')
parser.add_argument('--visu', action='store_true', help='Whether to dump image for error case [default: False]')
parser.add_argument('--num_votes', type=int, default=1, help='Aggregate classification scores from multiple rotations [default: 1]')
parser.add_argument('--num_drop', type=int, default=20, help='num of points to drop each step was 20   2/1')
parser.add_argument('--num_steps', type=int, default=2, help='num of steps to drop each step was 2   5/2')
parser.add_argument('--drop_neg', action='store_true',help='drop negative points')
parser.add_argument('--power', type=int, default=10, help='x: -dL/dr*r^x')
FLAGS = parser.parse_args()


BATCH_SIZE = FLAGS.batch_size
NUM_POINT = FLAGS.num_point
MODEL_PATH = FLAGS.model_path
GPU_INDEX = FLAGS.gpu
MODEL = importlib.import_module(FLAGS.model) # import network module
DUMP_DIR = FLAGS.dump_dir
if not os.path.exists(DUMP_DIR): os.mkdir(DUMP_DIR)
LOG_FOUT = open(os.path.join(DUMP_DIR, 'log_evaluate.txt'), 'w')
LOG_FOUT.write(str(FLAGS)+'\n')

NUM_CLASSES = 40
SHAPE_NAMES = ['white','black']

LOG_FOUTCN = open(os.path.join(DUMP_DIR, 'log_count.txt'), 'w')
LOG_FOUTCN.write(str(FLAGS)+'\n')

countPhen={}
countPhen[SHAPE_NAMES[0]] = []
countPhen[SHAPE_NAMES[1]] = []
countPhenCase={}
countPhenCase[SHAPE_NAMES[0]] = []
countPhenCase[SHAPE_NAMES[1]] = []
countPhenTis={}
countPhenTis[SHAPE_NAMES[0]] = []
countPhenTis[SHAPE_NAMES[1]] = []
countPhenTwo={}
countPhenTwo[SHAPE_NAMES[0]] = []
countPhenTwo[SHAPE_NAMES[1]] = []
countPhenVect={}
countPhenVect[SHAPE_NAMES[0]] = []
countPhenVect[SHAPE_NAMES[1]] = []

countPhenB={}
countPhenB[SHAPE_NAMES[0]] = []
countPhenB[SHAPE_NAMES[1]] = []
countPhenCaseB={}
countPhenCaseB[SHAPE_NAMES[0]] = []
countPhenCaseB[SHAPE_NAMES[1]] = []

xyzdata = 'randomBox60/log_box_60random5Rand_train.npy'
labeldata = 'randomBox60/log_box_60random5Rand_labeltrain.npy'
xyzdata_test = 'randomBox60/log_box_60random5Rand_test.npy'
labeldata_test = 'randomBox60/log_box_60random5Rand_label_test.npy'

#SHAPE_NAMES = [line.rstrip() for line in \
#    open(os.path.join(BASE_DIR, 'data/modelnet40_ply_hdf5_2048/shape_names.txt'))] 

HOSTNAME = socket.gethostname()

# ModelNet40 official train/test split
#TRAIN_FILES = provider.getDataFiles( \
#    os.path.join(BASE_DIR, 'data/modelnet40_ply_hdf5_2048/train_files.txt'))
#TEST_FILES = provider.getDataFiles(\
#    os.path.join(BASE_DIR, 'data/modelnet40_ply_hdf5_2048/test_files.txt'))

def log_string(out_str):
    LOG_FOUT.write(out_str+'\n')
    LOG_FOUT.flush()
    print(out_str)

def log_stringCN(out_str):
    LOG_FOUTCN.write(out_str+'\n')
    LOG_FOUTCN.flush()
    print(out_str)

class SphereAttack():
    def __init__(self, num_drop, num_steps):
        self.a = num_drop # how many points to remove
        self.k = num_steps
        
        self.is_training = False
        self.count = np.zeros((NUM_CLASSES, ), dtype=bool)
        self.all_counters = np.zeros((NUM_CLASSES, 3), dtype=int)
        
        # The number of points is not specified
        self.pointclouds_pl, self.labels_pl = MODEL.placeholder_inputs(BATCH_SIZE, None)
        self.is_training_pl = tf.placeholder(tf.bool, shape=())
        
        # simple model
        self.pred, self.end_points = MODEL.get_model(self.pointclouds_pl, self.is_training_pl)
        self.classify_loss = MODEL.get_loss_v2(self.pred, self.labels_pl, self.end_points)
        
        self.grad = tf.gradients(self.classify_loss, self.pointclouds_pl)[0]
        
        ## 3 folders to store all the situations
        if not os.path.exists(DUMP_DIR+'/pred_correct_adv_wrong'): os.mkdir(DUMP_DIR+'/pred_correct_adv_wrong')
        if not os.path.exists(DUMP_DIR+'/pred_wrong_adv_correct'): os.mkdir(DUMP_DIR+'/pred_wrong_adv_correct')
        if not os.path.exists(DUMP_DIR+'/pred_wrong_adv_wrong'): os.mkdir(DUMP_DIR+'/pred_wrong_adv_wrong')
        
    def drop_points(self, pointclouds_pl, labels_pl, sess):
        pointclouds_pl_adv = pointclouds_pl.copy()
        for i in range(self.k):
            grad = sess.run(self.grad, feed_dict={self.pointclouds_pl: pointclouds_pl_adv,
                                                  self.labels_pl: labels_pl,
                                                  self.is_training_pl: self.is_training})
            # change the grad into spherical axis and compute r*dL/dr
            ## mean value            
            #sphere_core = np.sum(pointclouds_pl_adv, axis=1, keepdims=True)/float(pointclouds_pl_adv.shape[1])
            ## median value
            sphere_core = np.median(pointclouds_pl_adv, axis=1, keepdims=True)
            
            sphere_r = np.sqrt(np.sum(np.square(pointclouds_pl_adv - sphere_core), axis=2)) ## BxN
            
            sphere_axis = pointclouds_pl_adv - sphere_core ## BxNx3

            if FLAGS.drop_neg:
                sphere_map = np.multiply(np.sum(np.multiply(grad, sphere_axis), axis=2), np.power(sphere_r, FLAGS.power))
            else:
                sphere_map = -np.multiply(np.sum(np.multiply(grad, sphere_axis), axis=2), np.power(sphere_r, FLAGS.power))

            drop_indice = np.argpartition(sphere_map, kth=sphere_map.shape[1]-self.a, axis=1)[:, -self.a:]

            tmp = np.zeros((pointclouds_pl_adv.shape[0], pointclouds_pl_adv.shape[1]-self.a, 3), dtype=float)
            for j in range(pointclouds_pl.shape[0]):
                tmp[j] = np.delete(pointclouds_pl_adv[j], drop_indice[j], axis=0) # along N points to delete
                
            pointclouds_pl_adv = tmp.copy()
            
        return pointclouds_pl_adv
    
    def plot_advsarial_samples(self, pointclouds_pl_adv, labels_pl, pred_val):
    
        for i in range(labels_pl.shape[0]):
        
            if labels_pl[i]!=pred_val[i] and not self.count[labels_pl[i]]:
            
                img_filename = 'label_%s_pred_%s.jpg' % (SHAPE_NAMES[labels_pl[i]],
                                                           SHAPE_NAMES[pred_val[i]])
                img_filename = os.path.join(DUMP_DIR, img_filename)
                
                pc_util.pyplot_draw_point_cloud(pointclouds_pl_adv[i], img_filename)
                
                self.count[labels_pl[i]] = True
                
    def plot_natural_and_advsarial_samples_all_situation(self, pointclouds_pl, pointclouds_pl_adv, labels_pl, pred_val, pred_val_adv,batch_idx,num_batches):
                
        for i in range(labels_pl.shape[0]):
            if labels_pl[i] == pred_val[i]:
                if labels_pl[i] != pred_val_adv[i]:
                    img_filename = 'label_%s_advpred_%s_%d' % (SHAPE_NAMES[labels_pl[i]],
                                                              SHAPE_NAMES[pred_val_adv[i]], 
                                                              self.all_counters[labels_pl[i]][0])
                    self.all_counters[labels_pl[i]][0] += 1
                    img_filename = os.path.join(DUMP_DIR+'/pred_correct_adv_wrong', img_filename)
                    #print('DATA pred_correct_adv_wrong: ', pointclouds_pl_adv[i][:,0], pointclouds_pl_adv[i][:,1], pointclouds_pl_adv[i][:,2] )
                    #exit()
                    if len(np.where(pointclouds_pl_adv[i][:,2] > 0)[0]) > 0 and len(np.where(pointclouds_pl_adv[i][:,2] < 11)[0]) > 0:
                        countPhenTis[SHAPE_NAMES[labels_pl[i]]].append('33')
                        #print('333333333333333 ',countPhenTis[SHAPE_NAMES[labels_pl[i]]], len(np.where( np.asarray(countPhenTis[SHAPE_NAMES[labels_pl[i]]]) == '33')[0]))
                        #print('COOR:  ',len(np.where(pointclouds_pl_adv[i][:,2] >=0)[0]),  pointclouds_pl_adv[i][:,0][0], pointclouds_pl_adv[i][:,1][0], pointclouds_pl_adv[i][:,2][0] )
                        #exit()
                        for pos in range(0,len(np.where(pointclouds_pl_adv[i][:,2] >=0)[0])):
                            if (pointclouds_pl_adv[i][:,2][pos] >0 and pointclouds_pl_adv[i][:,2][pos] <7) or pointclouds_pl_adv[i][:,2][pos]==9 or pointclouds_pl_adv[i][:,2][pos]==10 :
                                for posNext in range(pos+1,len(np.where(pointclouds_pl_adv[i][:,2] >=0)[0])):
                                    if (pointclouds_pl_adv[i][:,2][posNext] >0 and pointclouds_pl_adv[i][:,2][posNext] <7) or pointclouds_pl_adv[i][:,2][posNext]==9 or pointclouds_pl_adv[i][:,2][posNext]==10 :    
                                        vector = math.sqrt( (pointclouds_pl_adv[i][:,0][posNext] - pointclouds_pl_adv[i][:,0][pos])**2 + (pointclouds_pl_adv[i][:,1][posNext] - pointclouds_pl_adv[i][:,1][pos])**2 ) 
                                        #print ('POSTEST  ',pos,posNext, pointclouds_pl_adv[i][:,2])
                                        countPhenVect[SHAPE_NAMES[labels_pl[i]]].append(vector)
                                        #exit()
                    for counter in range(1,11):
                        #print(counter)
                        if len(np.where(pointclouds_pl_adv[i][:,2] == counter)[0]) > 0 :
                            countPhen[SHAPE_NAMES[labels_pl[i]]].append(counter)
                            for add in range(1,len(np.where(pointclouds_pl_adv[i][:,2] == counter)[0])+1):
                                #print (add, len(np.where(pointclouds_pl_adv[i][:,2] == counter)[0]))
                                countPhenCase[SHAPE_NAMES[labels_pl[i]]].append(counter)
                    for counterA in range(1,11):              
                        if len(np.where(pointclouds_pl_adv[i][:,2] == counterA)[0]) > 0 :
                            for counterB in range(counterA+1,11):
                                #print(counter)
                                if len(np.where(pointclouds_pl_adv[i][:,2] == counterB)[0]) > 0 :
                                    #print ('TWOarr   ',counterA, counterB)
                                    countPhenTwo[SHAPE_NAMES[labels_pl[i]]].append("-".join((str(counterA), str(counterB))))
                    
                    pc_util.pyplot_draw_point_cloud_nat_and_adv(pointclouds_pl[i], pointclouds_pl_adv[i], img_filename)    
            else:
                if labels_pl[i] == pred_val_adv[i]:
                    img_filename = 'label_%s_pred_%s_%d' % (SHAPE_NAMES[labels_pl[i]],
                                                              SHAPE_NAMES[pred_val[i]], 
                                                              self.all_counters[labels_pl[i]][1])
                    self.all_counters[labels_pl[i]][1] += 1        
                    img_filename = os.path.join(DUMP_DIR+'/pred_wrong_adv_correct', img_filename)
                    #print('DATA pred_wrong_adv_correct: ', self.all_counters[labels_pl[i]][1] )
                    for counter in range(1,17):
                        #print(counter)
                        if len(np.where(pointclouds_pl_adv[i][:,2] == counter)[0]) > 0 :
                            countPhenB[SHAPE_NAMES[labels_pl[i]]].append(counter)
                            for add in range(1,len(np.where(pointclouds_pl_adv[i][:,2] == counter)[0])+1):
                                #print (add, len(np.where(pointclouds_pl_adv[i][:,2] == counter)[0]))
                                countPhenCaseB[SHAPE_NAMES[labels_pl[i]]].append(counter)
                #else:
            
                    #img_filename = 'label_%s_pred_%s_advpred_%s_%d' % (SHAPE_NAMES[labels_pl[i]],
                    #                                          SHAPE_NAMES[pred_val[i]],
                    #                                          SHAPE_NAMES[pred_val_adv[i]],
                    #                                          self.all_counters[labels_pl[i]][2])
                    #self.all_counters[labels_pl[i]][2] += 1
                    #img_filename = os.path.join(DUMP_DIR+'/pred_wrong_adv_wrong', img_filename)
                
                    pc_util.pyplot_draw_point_cloud_nat_and_adv(pointclouds_pl[i], pointclouds_pl_adv[i], img_filename)
        print('BATCH=============',batch_idx, num_batches)
        if batch_idx+1 == num_batches:
            #print(' count phenotype: ',countPhen,countPhen[SHAPE_NAMES[0]])
            log_stringCN ('========pred_correct_adv_wrong==========================================================================================')
            log_stringCN(' Vectors: %s%s' % (SHAPE_NAMES[0], countPhenVect[SHAPE_NAMES[0]]))
            log_stringCN(' Vectors: %s%s' % (SHAPE_NAMES[1], countPhenVect[SHAPE_NAMES[1]]))
            log_stringCN(' Tiles: %s%s' % (SHAPE_NAMES[0], len(np.where( np.asarray(countPhenTis[SHAPE_NAMES[0]]) == '33')[0])))
            #print(' Tiles:  ', SHAPE_NAMES[0], len(np.where( np.asarray(countPhenTis[SHAPE_NAMES[0]]) >0)[0]))
            log_stringCN(' Tiles: %s%s' % (SHAPE_NAMES[1],len(np.where( np.asarray(countPhenTis[SHAPE_NAMES[1]]) == '33')[0])))        
            log_stringCN('Below: In tile, ratio in tile, avg amount in tile')
            for counter in range(1,11):
                log_stringCN (' Phenotype:  %s%s' % (SHAPE_NAMES[0], counter))
                log_stringCN ('%s' % (len(np.where( np.asarray(countPhen[SHAPE_NAMES[0]]) == counter)[0]) ))
                if (len(np.where( np.asarray(countPhenTis[SHAPE_NAMES[0]]) =='33')[0]) >0):
                    log_stringCN ('%s' % (float(len(np.where( np.asarray(countPhen[SHAPE_NAMES[0]]) == counter)[0]))/(len(np.where( np.asarray(countPhenTis[SHAPE_NAMES[0]]) =='33')[0]))) )
                else:   log_stringCN ('0')
                if len(np.where( np.asarray(countPhen[SHAPE_NAMES[0]]) == counter)[0]) > 0:
                    log_stringCN ('%s' % (float(len(np.where( np.asarray(countPhenCase[SHAPE_NAMES[0]]) == counter)[0]))/(len(np.where( np.asarray(countPhen[SHAPE_NAMES[0]]) == counter)[0]))) )
                    #print (float(len(np.where( np.asarray(countPhenCase[SHAPE_NAMES[0]]) == counter)[0]))/(len(np.where( np.asarray(countPhen[SHAPE_NAMES[0]]) >0)[0])) )
                else:   log_stringCN ('0')
            for counter in range(1,11):
                log_stringCN (' Phenotype:  %s%s' % (SHAPE_NAMES[1], counter))
                log_stringCN ('%s' % (len(np.where( np.asarray(countPhen[SHAPE_NAMES[1]]) == counter)[0]) ))
                if (len(np.where( np.asarray(countPhenTis[SHAPE_NAMES[1]]) =='33')[0]) >0):
                    log_stringCN ('%s' % (float(len(np.where( np.asarray(countPhen[SHAPE_NAMES[1]]) == counter)[0]))/(len(np.where( np.asarray(countPhenTis[SHAPE_NAMES[1]]) =='33')[0]))) )
                else:   log_stringCN ('0')
                if len(np.where( np.asarray(countPhen[SHAPE_NAMES[1]]) == counter)[0]) > 0:
                    log_stringCN ('%s' % (float(len(np.where( np.asarray(countPhenCase[SHAPE_NAMES[1]]) == counter)[0]))/(len(np.where( np.asarray(countPhen[SHAPE_NAMES[1]]) == counter)[0]))) )
                    #print (float(len(np.where( np.asarray(countPhenCase[SHAPE_NAMES[1]]) == counter)[0]))/(len(np.where( np.asarray(countPhen[SHAPE_NAMES[1]]) >0)[0])) )
                else:   log_stringCN ('0')
            for counterA in range(1,11):
                for counterB in range(counterA+1,11):
                    #print (' Phenotype Two:  ',SHAPE_NAMES[0], counterA, counterB)
                    #print (len(np.where( np.asarray(countPhenTwo[SHAPE_NAMES[0]]) == "-".join((str(counterA), str(counterB))) )[0]) )
                    if (len(np.where( np.asarray(countPhenTis[SHAPE_NAMES[0]]) =='33')[0]) > 0) and (len(np.where( np.asarray(countPhenTwo[SHAPE_NAMES[0]]) == "-".join((str(counterA), str(counterB))) )[0]) >0 ):
                        ##log_stringCN (' Phenotype Two:  %s%s%s' % (SHAPE_NAMES[0], counterA, counterB))
                        ##log_stringCN ('%s' % (len(np.where( np.asarray(countPhenTwo[SHAPE_NAMES[0]]) == "-".join((str(counterA), str(counterB))) )[0])) )                    
                        log_stringCN ('%s%s%s%s%s' % (float(len(np.where( np.asarray(countPhenTwo[SHAPE_NAMES[0]]) == "-".join((str(counterA), str(counterB))) )[0]))/(len(np.where( np.asarray(countPhenTis[SHAPE_NAMES[0]]) =='33')[0])),'-',SHAPE_NAMES[0], counterA, counterB) )
            for counterA in range(1,11):
                for counterB in range(counterA+1,11):
                    #print (' Phenotype Two:  ',SHAPE_NAMES[1], counterA, counterB)
                    #print (len(np.where( np.asarray(countPhenTwo[SHAPE_NAMES[1]]) == "-".join((str(counterA), str(counterB))) )[0]) )
                    if (len(np.where( np.asarray(countPhenTis[SHAPE_NAMES[1]]) =='33')[0]) > 0) and (len(np.where( np.asarray(countPhenTwo[SHAPE_NAMES[1]]) == "-".join((str(counterA), str(counterB))) )[0]) >0 ):
                        ##log_stringCN (' Phenotype Two:  %s%s%s' % (SHAPE_NAMES[1], counterA, counterB))
                        ##log_stringCN ('%s' % (len(np.where( np.asarray(countPhenTwo[SHAPE_NAMES[1]]) == "-".join((str(counterA), str(counterB))) )[0])) )
                        log_stringCN ('%s%s%s%s%s' % (float(len(np.where( np.asarray(countPhenTwo[SHAPE_NAMES[1]]) == "-".join((str(counterA), str(counterB))) )[0]))/(len(np.where( np.asarray(countPhenTis[SHAPE_NAMES[1]]) =='33')[0])),'-',SHAPE_NAMES[1], counterA, counterB) )
 
            #print ('========pred_wrong_adv_correct==========================================================================================')
            #print(' Tiles: ',SHAPE_NAMES[0],len(np.where( np.asarray(countPhenB[SHAPE_NAMES[0]]) >0)[0]))
            #print(' Tiles: ',SHAPE_NAMES[1],len(np.where( np.asarray(countPhenB[SHAPE_NAMES[1]]) >0)[0]))
            #print('Below: In tile, ratio in tile, avg amount in tile')
            #for counter in range(1,17):3
                #print (' Phenotype:  ',SHAPE_NAMES[0], counter)
                #print (len(np.where( np.asarray(countPhenB[SHAPE_NAMES[0]]) == counter)[0]) )
                #if (len(np.where( np.asarray(countPhenB[SHAPE_NAMES[0]]) >0)[0]) > 0):
                    #print (float(len(np.where( np.asarray(countPhenB[SHAPE_NAMES[0]]) == counter)[0]))/(len(np.where( np.asarray(countPhenB[SHAPE_NAMES[0]]) >0)[0])) )
                #if len(np.where( np.asarray(countPhenB[SHAPE_NAMES[0]]) == counter)[0]) > 0:
                    #print (float(len(np.where( np.asarray(countPhenCaseB[SHAPE_NAMES[0]]) == counter)[0]))/(len(np.where( np.asarray(countPhenB[SHAPE_NAMES[0]]) == counter)[0])) )
                    ##print (float(len(np.where( np.asarray(countPhenCaseB[SHAPE_NAMES[0]]) == counter)[0]))/(len(np.where( np.asarray(countPhenB[SHAPE_NAMES[0]]) >0)[0])) )
            #for counter in range(1,17):
                #print (' Phenotype:  ',SHAPE_NAMES[1], counter)
                #print (len(np.where( np.asarray(countPhenB[SHAPE_NAMES[1]]) == counter)[0]) )
                #if (len(np.where( np.asarray(countPhenB[SHAPE_NAMES[1]]) >0)[0]) > 0):
                    #print (float(len(np.where( np.asarray(countPhenB[SHAPE_NAMES[1]]) == counter)[0]))/(len(np.where( np.asarray(countPhenB[SHAPE_NAMES[1]]) >0)[0])) )
                #if len(np.where( np.asarray(countPhenB[SHAPE_NAMES[1]]) == counter)[0]) > 0:    
                    #print (float(len(np.where( np.asarray(countPhenCaseB[SHAPE_NAMES[1]]) == counter)[0]))/(len(np.where( np.asarray(countPhenB[SHAPE_NAMES[1]]) == counter)[0])) )
                    ##print (float(len(np.where( np.asarray(countPhenCaseB[SHAPE_NAMES[1]]) == counter)[0]))/(len(np.where( np.asarray(countPhenB[SHAPE_NAMES[1]]) >0)[0])) )


def evaluate(num_votes):
    is_training = False
    num_drop, num_steps = FLAGS.num_drop, FLAGS.num_steps
    attack = SphereAttack(num_drop, num_steps)
        
    # Add ops to save and restore all the variables.
    saver = tf.train.Saver()
        
    # Create a session
    config = tf.ConfigProto()
    config.gpu_options.allow_growth = True
    config.allow_soft_placement = True
    config.log_device_placement = True
    sess = tf.Session(config=config)
    #print (config,sess)
    #exit()

    # Restore variables from disk.
    saver.restore(sess, MODEL_PATH)
    log_string("Model restored.")

    ## ops built on attributes defined in attack
    ops = {'pointclouds_pl': attack.pointclouds_pl,
           'labels_pl': attack.labels_pl,
           'is_training_pl': attack.is_training_pl,
           'pred': attack.pred,
           'loss': attack.classify_loss}

    NUM_POINT = FLAGS.num_point
    NUM_POINT_ADV = NUM_POINT - num_drop*num_steps
    
    error_cnt = 0
    is_training = False
    total_correct = 0
    total_seen = 0
    loss_sum = 0
    total_seen_class = [0 for _ in range(NUM_CLASSES)]
    total_correct_class = [0 for _ in range(NUM_CLASSES)]
    fout = open(os.path.join(DUMP_DIR, 'pred_label.txt'), 'w')
    all_data,all_label=np.load(xyzdata),np.load(labeldata)
    print(np.shape(all_data),np.shape(all_label))
    for fn in range(1):
    #for fn in range(len(TEST_FILES)):
        log_string('----'+str(fn)+'----')
        #print (fn)
        #exit()
        current_data, current_label = all_data[:,:,:],all_label[:]
        #current_data, current_label = provider.loadDataFile(TEST_FILES[fn])
        current_data = current_data[:,0:NUM_POINT,:]
        current_label = np.squeeze(current_label)
        print(current_data.shape)
        
        file_size = current_data.shape[0]
        num_batches = file_size // BATCH_SIZE
        print(file_size)
        
        for batch_idx in range(num_batches):
            start_idx = batch_idx * BATCH_SIZE
            end_idx = (batch_idx+1) * BATCH_SIZE
            cur_batch_size = end_idx - start_idx
            
            # Aggregating BEG
            batch_loss_sum = 0 # sum of losses for the batch
            batch_pred_sum = np.zeros((cur_batch_size, NUM_CLASSES)) # score for classes
            batch_pred_classes = np.zeros((cur_batch_size, NUM_CLASSES)) # 0/1 for classes
            
            ## Produce adversarial samples
            cur_batch_data_adv = attack.drop_points(current_data[start_idx:end_idx, :, :], 
                                                    current_label[start_idx:end_idx], sess)
            ## Natural data
            for vote_idx in range(num_votes):
                rotated_data = provider.rotate_point_cloud_by_angle(current_data[start_idx:end_idx, :, :],
                                                  vote_idx/float(num_votes) * np.pi * 2)
                feed_dict = {ops['pointclouds_pl']: rotated_data,
                             ops['labels_pl']: current_label[start_idx:end_idx],
                             ops['is_training_pl']: is_training}
                loss_val, pred_val = sess.run([ops['loss'], ops['pred']],
                                          feed_dict=feed_dict)
                batch_pred_sum += pred_val
                batch_pred_val = np.argmax(pred_val, 1)
                for el_idx in range(cur_batch_size):
                    batch_pred_classes[el_idx, batch_pred_val[el_idx]] += 1
                batch_loss_sum += (loss_val * cur_batch_size / float(num_votes))
            pred_val = np.argmax(batch_pred_sum, 1)
            
            ## Adversarial data
            
            batch_loss_sum_adv = 0 # sum of losses for the batch
            batch_pred_sum_adv = np.zeros((cur_batch_size, NUM_CLASSES)) # score for classes
            batch_pred_classes_adv = np.zeros((cur_batch_size, NUM_CLASSES)) # 0/1 for classes
            
            for vote_idx in range(num_votes):
                rotated_data = provider.rotate_point_cloud_by_angle(cur_batch_data_adv,
                                                  vote_idx/float(num_votes) * np.pi * 2)
                feed_dict = {ops['pointclouds_pl']: rotated_data,
                             ops['labels_pl']: current_label[start_idx:end_idx],
                             ops['is_training_pl']: is_training}
                loss_val_adv, pred_val_adv = sess.run([ops['loss'], ops['pred']],
                                          feed_dict=feed_dict)
                batch_pred_sum_adv += pred_val_adv
                batch_pred_val_adv = np.argmax(pred_val_adv, 1)
                for el_idx in range(cur_batch_size):
                    batch_pred_classes_adv[el_idx, batch_pred_val_adv[el_idx]] += 1
                batch_loss_sum_adv += (loss_val_adv * cur_batch_size / float(num_votes))
            pred_val_adv = np.argmax(batch_pred_sum_adv, 1)

            attack.plot_advsarial_samples(current_data[start_idx:end_idx, :, :],current_label[start_idx:end_idx], pred_val)
            ###
            attack.plot_natural_and_advsarial_samples_all_situation(current_data[start_idx:end_idx, :, :], cur_batch_data_adv, 
                                                      current_label[start_idx:end_idx], pred_val, pred_val_adv,batch_idx,num_batches)
            correct = np.sum(pred_val_adv == current_label[start_idx:end_idx])
            # correct = np.sum(pred_val_topk[:,0:topk] == label_val)
            total_correct += correct
            total_seen += cur_batch_size
            loss_sum += batch_loss_sum_adv

            for i in range(start_idx, end_idx):
                l = current_label[i]
                total_seen_class[l] += 1
                total_correct_class[l] += (pred_val_adv[i-start_idx] == l)
                fout.write('%d, %d\n' % (pred_val_adv[i-start_idx], l))
                
                # if pred_val[i-start_idx] != l and FLAGS.visu: # ERROR CASE, DUMP!
                    # img_filename = '%d_label_%s_pred_%s.jpg' % (error_cnt, SHAPE_NAMES[l],
                                                           # SHAPE_NAMES[pred_val[i-start_idx]])
                    # img_filename = os.path.join(DUMP_DIR, img_filename)
                    # output_img = pc_util.point_cloud_three_views(np.squeeze(current_data[i, :, :]))
                    # scipy.misc.imsave(img_filename, output_img)
                    # error_cnt += 1
                
    log_string('eval mean loss: %f' % (loss_sum / float(total_seen)))
    log_string('eval accuracy: %f' % (total_correct / float(total_seen)))
    log_string('eval avg class acc: %f' % (np.mean(np.array(total_correct_class)/np.array(total_seen_class,dtype=np.float))))
    
    class_accuracies = np.array(total_correct_class)/np.array(total_seen_class,dtype=np.float)
    for i, name in enumerate(SHAPE_NAMES):
        log_string('%10s:\t%0.3f' % (name, class_accuracies[i]))
    


if __name__=='__main__':
    with tf.Graph().as_default():
        evaluate(num_votes=FLAGS.num_votes)
    LOG_FOUT.close()


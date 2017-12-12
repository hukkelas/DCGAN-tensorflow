from __future__ import division
import os
import time
import math
from glob import glob
import tensorflow as tf
import numpy as np
from six.moves import xrange
import scipy.misc
from ops import *
from utils import *
import matplotlib.pyplot as plt 
import csv
from sklearn.preprocessing import OneHotEncoder
def conv_out_size_same(size, stride):
  return int(math.ceil(float(size) / float(stride)))

class DCGAN(object):
  def __init__(self, sess, crop=True,
         batch_size=64, sample_num = 64,
         y_dim=None, z_dim=100, gf_dim=64, df_dim=64,
         gfc_dim=1024, dfc_dim=1024, c_dim=3, dataset_name='default',
         input_fname_pattern='*.jpg', checkpoint_dir=None, sample_dir=None, imsize= 28,
        gen_activation_function=tf.nn.tanh, model="fc"):
    """

    Args:
      sess: TensorFlow session
      batch_size: The size of batch. Should be specified before training.
      y_dim: (optional) Dimension of dim for y. [None]
      z_dim: (optional) Dimension of dim for Z. [100]
      gf_dim: (optional) Dimension of gen filters in first conv layer. [64]
      df_dim: (optional) Dimension of discrim filters in first conv layer. [64]
      gfc_dim: (optional) Dimension of gen units for for fully connected layer. [1024]
      dfc_dim: (optional) Dimension of discrim units for fully connected layer. [1024]
      c_dim: (optional) Dimension of image color. For grayscale input, set to 1. [3]
      model: (optional) Fully connected or convolutional [fc, cond]
    """
    self.model = model
    self.sess = sess
    self.gen_activation_function = gen_activation_function
    self.batch_size = batch_size
    
    self.imsize = imsize

    self.y_dim = y_dim
    self.z_dim = z_dim
    self.sample_num = 5

    self.gf_dim = gf_dim
    self.df_dim = df_dim

    self.gfc_dim = gfc_dim
    self.dfc_dim = dfc_dim

    # batch normalization : deals with poor initialization helps gradient flow
    self.d_bn1 = batch_norm(name='d_bn1')
    self.d_bn2 = batch_norm(name='d_bn2')


    self.d_bn3 = batch_norm(name='d_bn3')

    self.g_bn0 = batch_norm(name='g_bn0')
    self.g_bn1 = batch_norm(name='g_bn1')
    self.g_bn2 = batch_norm(name='g_bn2')


    self.g_bn3 = batch_norm(name='g_bn3')

    self.dataset_name = dataset_name
    self.input_fname_pattern = input_fname_pattern
    self.checkpoint_dir = checkpoint_dir

    if self.dataset_name == 'mnist':
      self.data_X, self.data_y = self.load_mnist()
      self.c_dim = self.data_X[0].shape[-1]

    if self.dataset_name == 'pokemon/64x64x3':
      self.data_y = self.load_pokemon_y()
      self.data = glob(os.path.join("./data", self.dataset_name, self.input_fname_pattern))
      selected = [199, 196, 210, 238, 240, 239, 237, 224, 378, 377, 370, 364, 390, 376, 438, 454, 450, 449,
                  291, 317, 335, 402, 423, 466, 479, 518, 529, 581, 609, 655, 646, 743, 754, 753, 735, 749]
      self.data_X = np.zeros((802,self.imsize, self.imsize, c_dim))
      #print self.data_y[0:6] * np.arange(1,19)
      self.data_y = self.data_y#[selected]
      
      for path in self.data:
        i = int(path.split("/")[-1].split(".")[0]) -1 
        im = imread(path)
        self.data_X[i] = im / 255
      self.data_X = self.data_X#[selected]
      
      imreadImg = imread(self.data[0])
      if len(imreadImg.shape) >= 3: #check if image is a non-grayscale image by checking channel number
        self.c_dim = imread(self.data[0]).shape[-1]
      else:
        self.c_dim = 1
    else:
      self.data = glob(os.path.join("./data", self.dataset_name, self.input_fname_pattern))

      imreadImg = imread(self.data[0])
      if len(imreadImg.shape) >= 3: #check if image is a non-grayscale image by checking channel number
        self.c_dim = imread(self.data[0]).shape[-1]
      else:
        self.c_dim = 1

    self.grayscale = (self.c_dim == 1)

    self.build_model()

  def build_model(self):
    if self.y_dim:
      self.y = tf.placeholder(tf.float32, [None, self.y_dim], name='y')
    else:
      self.y = None


    image_dims = [self.imsize, self.imsize, self.c_dim]

    self.inputs = tf.placeholder(
      tf.float32, [self.batch_size] + image_dims, name='real_images')

    inputs = self.inputs

    self.z = tf.placeholder(
      tf.float32, [None, self.z_dim], name='z')
    self.z_sum = histogram_summary("z", self.z)

    self.G                  = self.generator(self.z, self.y)
    self.D, self.D_logits   = self.discriminator(inputs, self.y, reuse=False)
    self.sampler            = self.sampler(self.z, self.y)
    self.D_, self.D_logits_ = self.discriminator(self.G, self.y, reuse=True)
    
    self.d_sum = histogram_summary("d", self.D)
    self.d__sum = histogram_summary("d_", self.D_)
    self.G_sum = image_summary("G", self.G)

    def sigmoid_cross_entropy_with_logits(x, y):
      try:
        return tf.nn.sigmoid_cross_entropy_with_logits(logits=x, labels=y)
      except:
        return tf.nn.sigmoid_cross_entropy_with_logits(logits=x, targets=y)
    
    self.d_loss_real = tf.reduce_mean(
      sigmoid_cross_entropy_with_logits(self.D_logits, tf.ones_like(self.D)))
    self.d_loss_fake = tf.reduce_mean(
      sigmoid_cross_entropy_with_logits(self.D_logits_, tf.zeros_like(self.D_)))
    self.g_loss = tf.reduce_mean(
      sigmoid_cross_entropy_with_logits(self.D_logits_, tf.ones_like(self.D_)))
    
    self.accuracy_real = tf.reduce_mean(tf.cast(tf.equal(tf.squeeze(tf.round(self.D)), tf.ones_like(self.D)), tf.float32))
    self.accuracy_fake = tf.reduce_mean(tf.cast(tf.equal(tf.squeeze(tf.round(self.D_)), tf.zeros_like(self.D)), tf.float32))
    
    self.d_loss_real_sum = scalar_summary("d_loss_real", self.d_loss_real)
    self.d_loss_fake_sum = scalar_summary("d_loss_fake", self.d_loss_fake)
                          
    self.d_loss = self.d_loss_real + self.d_loss_fake

    self.g_loss_sum = scalar_summary("g_loss", self.g_loss)
    self.d_loss_sum = scalar_summary("d_loss", self.d_loss)

    t_vars = tf.trainable_variables()

    self.d_vars = [var for var in t_vars if 'd_' in var.name]
    self.g_vars = [var for var in t_vars if 'g_' in var.name]

    self.saver = tf.train.Saver()

  def train(self, config):
#    for i,im in enumerate(self.data_X):
#        print np.arange(1,19) * self.data_y[i]
#        plt.imshow(im)
#        plt.show()
    # Optimizers
    d_optim = tf.train.AdamOptimizer(config.learning_rate, beta1=config.beta1) \
              .minimize(self.d_loss, var_list=self.d_vars)
    g_optim = tf.train.AdamOptimizer(config.learning_rate, beta1=config.beta1) \
              .minimize(self.g_loss, var_list=self.g_vars)
    
    tf.global_variables_initializer().run()

    # 
    self.g_sum = merge_summary([self.z_sum, self.d__sum,
      self.G_sum, self.d_loss_fake_sum, self.g_loss_sum])

    self.d_sum = merge_summary(
        [self.z_sum, self.d_sum, self.d_loss_real_sum, self.d_loss_sum])
    

    sample_z = np.random.uniform(-1, 1, size=(self.sample_num*self.y_dim , self.z_dim))
    
    samples = [[j] for j in range(self.y_dim) for i in range(self.sample_num)]
    oh = OneHotEncoder()
    oh.fit(samples)
    
    sample_labels = oh.transform(samples).toarray()

    # Load sample data
    '''
    if config.dataset == 'pokemon/64x64x3':
      sample_labels = self.data_y[0:self.sample_num]
    if config.dataset == 'mnist':
      sample_inputs = self.data_X[0:self.sample_num]
      sample_labels = self.data_y[0:self.sample_num]
    else:
      sample_files = self.data[0:self.sample_num]
      sample = [
          get_image(sample_file,
                    input_height=self.imsize,
                    input_width=self.imsize,
                    resize_height=self.imsize,
                    resize_width=self.imsize,
                    crop=False,
                    grayscale=self.grayscale) for sample_file in sample_files]
      if (self.grayscale):
        sample_inputs = np.array(sample).astype(np.float32)[:, :, :, None]
      else:
        sample_inputs = np.array(sample).astype(np.float32)
    '''
    counter = 1
    start_time = time.time()
    # Load checkpoint
    could_load, checkpoint_counter = self.load(self.checkpoint_dir)
    if could_load:
      counter = checkpoint_counter
      print(" [*] Load SUCCESS")
    else:
      print(" [!] Load failed...")

    # Start training
    for epoch in xrange(config.epoch):
      
      if config.dataset == 'mnist':
        batch_idxs = min(len(self.data_X), config.train_size) // self.batch_size
      else:      
        self.data = glob(os.path.join(
          "./data", config.dataset, self.input_fname_pattern))
        batch_idxs = min(len(self.data), config.train_size) // self.batch_size

      for idx in xrange(0, batch_idxs):
        # Set batch X and Y
        if config.dataset == 'pokemon/64x64x3':
          random_idxs = np.random.randint(0,len(self.data_X), self.batch_size)
          batch_labels = self.data_y[random_idxs]
          batch_images = self.data_X[random_idxs]
        if config.dataset == 'mnist':
          batch_images = self.data_X[idx*config.batch_size:(idx+1)*config.batch_size]
          batch_labels = self.data_y[idx*config.batch_size:(idx+1)*config.batch_size]
        if False:
          random_idxs = np.random.randint(0,len(self.data_X), self.batch_size)
          batch = self.data_X[random_idxs]
          #self.data_X[idx*config.batch_size:(idx+1)*config.batch_size]
          if self.grayscale:
            batch_images = np.array(batch).astype(np.float32)[:, :, :, None]
          else:
            batch_images = np.array(batch).astype(np.float32)

        batch_z = np.random.uniform(-1, 1, [self.batch_size, self.z_dim]).astype(np.float32)
        
              
        # Update each dataset
        if config.dataset == 'mnist':
          # Update D network
          _, summary_str = self.sess.run([d_optim, self.d_sum],
            feed_dict={ 
              self.inputs: batch_images,
              self.z: batch_z,
              self.y:batch_labels,
            })


          # Update G network
          _, summary_str = self.sess.run([g_optim, self.g_sum],
            feed_dict={
              self.z: batch_z, 
              self.y: batch_labels,
            })

          # Run g_optim twice to make sure that d_loss does not go to zero (different from paper)
          _, summary_str = self.sess.run([g_optim, self.g_sum],
            feed_dict={ self.z: batch_z, self.y:batch_labels })

          
          errD_fake = self.d_loss_fake.eval({
              self.z: batch_z, 
              self.y:batch_labels
          })
          errD_real = self.d_loss_real.eval({
              self.inputs: batch_images,
              self.y:batch_labels
          })
          errG = self.g_loss.eval({
              self.z: batch_z,
              self.y: batch_labels
          })
        else:
          # Update D network
          _, summary_str = self.sess.run([d_optim, self.d_sum],
            feed_dict={ self.inputs: batch_images, self.z: batch_z, self.y: batch_labels })

          # Update G network
          _, summary_str = self.sess.run([g_optim, self.g_sum],
            feed_dict={ self.z: batch_z, self.y:batch_labels })

          # Run g_optim twice to make sure that d_loss does not go to zero (different from paper)
          _, summary_str = self.sess.run([g_optim, self.g_sum],
            feed_dict={ self.z: batch_z, self.y: batch_labels })

        counter += 1

      if epoch % 10 == 0:
        # Gather statistics 
        errD_fake, errD_real, errG, acc_real, acc_fake = self.sess.run(
          [self.d_loss_fake, self.d_loss_real , self.g_loss, self.accuracy_real, self.accuracy_fake],
          feed_dict={self.inputs: batch_images, self.y: batch_labels, self.z: batch_z}
          )
        print "Epoch:{:4d}, time:{:6.1f}, d_real_loss:{:1.4f}, d_fake_loss:{:1.4f}, g_loss:{:2.4f}, acc_real:{:0.3f}, acc_fake:{:0.3f}" \
          .format(epoch, time.time() - start_time, errD_real, errD_fake, errG, acc_real, acc_fake)

        # Save losses
        f = open('{}/curve.txt'.format(config.sample_dir), 'a')
        f.write("{},{},{},{},{}\n".format(errG, errD_fake, errD_real, acc_real, acc_fake) ) 
        f.close()

        if epoch % 100 == 0:
          self.save(config.checkpoint_dir, counter)

        if config.dataset == 'mnist' or True:
          samples, = self.sess.run(
            [self.sampler],
            feed_dict={
                self.z: sample_z,
                self.y: sample_labels,
            }
          )      
          save_images(samples, image_manifold_size(samples.shape[0]),
                './{}/train_{:02d}.png'.format(config.sample_dir, epoch), column_size=self.sample_num)
          print("Sample saved") 
        else:
          try:
            samples, d_loss, g_loss = self.sess.run(
              [self.sampler, self.d_loss, self.g_loss],
              feed_dict={
                  self.z: sample_z,
                  self.inputs: sample_inputs,
              },
            )
            
            print "Max value:" , samples.max()
            print "Min value:", samples.min()
            save_images(samples, image_manifold_size(samples.shape[0]),
                  './{}/train_{:02d}.png'.format(config.sample_dir, epoch))
            print("[Sample] d_loss: %.8f, g_loss: %.8f" % (d_loss, g_loss)) 
          except:
            print("one pic error!...")


  def discriminator(self, image, y=None, reuse=False):
    with tf.variable_scope("discriminator") as scope:
      if reuse:
        scope.reuse_variables()

      if not self.y_dim:
        h0 = lrelu(conv2d(image, self.df_dim, name='d_h0_conv'))
        h1 = lrelu(self.d_bn1(conv2d(h0, self.df_dim*2, name='d_h1_conv')))
        h2 = lrelu(self.d_bn2(conv2d(h1, self.df_dim*4, name='d_h2_conv')))
        h3 = lrelu(self.d_bn3(conv2d(h2, self.df_dim*8, name='d_h3_conv')))
        h4 = linear(tf.reshape(h3, [self.batch_size, -1]), 1, 'd_h4_lin')

        return tf.nn.sigmoid(h4), h4
      else:
        yb = tf.reshape(y, [self.batch_size, 1, 1, self.y_dim])
        x = conv_cond_concat(image, yb)

        h0 = lrelu(conv2d(x, self.c_dim + self.y_dim, name='d_h0_conv'))
        h0 = conv_cond_concat(h0, yb)

        h1 = lrelu(self.d_bn1(conv2d(h0, self.df_dim + self.y_dim, name='d_h1_conv')))
        h1 = tf.reshape(h1, [self.batch_size, -1])      
        h1 = concat([h1, y], 1)
        
        h2 = lrelu(self.d_bn2(linear(h1, self.dfc_dim, 'd_h2_lin')))
        h2 = concat([h2, y], 1)

        h3 = linear(h2, 1, 'd_h3_lin')
        
        return tf.nn.sigmoid(h3), h3
  
  def create_generator(self, z, size, y=None, reuse=False):
    with tf.variable_scope("generator") as scope:
      if reuse:
        scope.reuse_variables()
      if self.model=='fc' and self.y_dim:
        return self.create_cond_fcgan_generator(z,size,y)
      elif self.model=='cond' and self.y_dim:
        return self.create_cond_dcgan_generator(z, size, y)
      else:
        return self.create_dcgan_generator(z, size, y)

  def create_cond_fcgan_generator(self, z, size, y):
    # Input sizes
    s_h, s_w = self.imsize, self.imsize
    s_h2, s_h4 = int(s_h/2), int(s_h/4)
    s_w2, s_w4 = int(s_w/2), int(s_w/4)


    yb = tf.reshape(y, [size, 1, 1, self.y_dim])
    # shape: [batch_size, y_dim + z_dim]
    z = concat([z, y], 1)

    # fc1 layer
    h0 = linear(
      input_=z,
      output_size=self.gfc_dim,
      scope="g_h0_lin"
    )
    # Relu
    h0 = tf.nn.relu(self.g_bn0(h0))
    # Concatenate
    # From 1024 -> 1042
    h0 = concat([h0, y], 1)

    # FC 2 
    h1 = tf.nn.relu(self.g_bn1(
        linear(h0, self.gf_dim*2*s_h4*s_w4, 'g_h1_lin')))
    h1 = tf.reshape(h1, [size, s_h4, s_w4, self.gf_dim * 2])
    
    h1 = conv_cond_concat(h1, yb)
    # FC 3 
    h2 = tf.nn.relu(self.g_bn2(deconv2d(h1,
        [size, s_h2, s_w2, self.gf_dim * 2], name='g_h2')))
    h2 = conv_cond_concat(h2, yb)
    h3 = deconv2d(h2, [size, s_h, s_w, self.c_dim], name='g_h3')

    return self.gen_activation_function(h3)

  def create_cond_dcgan_generator(self, z, size, y=None):
    s_h, s_w = self.imsize, self.imsize

    # Define input sizes for convolutions
    s_h2, s_w2 = conv_out_size_same(s_h, 2), conv_out_size_same(s_w, 2)
    s_h4, s_w4 = conv_out_size_same(s_h2, 2), conv_out_size_same(s_w2, 2)
    s_h8, s_w8 = conv_out_size_same(s_h4, 2), conv_out_size_same(s_w4, 2)
    s_h16, s_w16 = conv_out_size_same(s_h8, 2), conv_out_size_same(s_w8, 2)

    yb = tf.reshape(y, [size, 1, 1, self.y_dim])
    z = concat([z, y], 1)

    # project `z` and reshape
    self.z_, self.h0_w, self.h0_b = linear(
        input_=z,
        output_size=self.gf_dim*8*s_h16*s_w16,
        scope='g_h0_lin', 
        with_w=True)

    self.h0 = tf.reshape(
        self.z_, [size, s_h16, s_w16, self.gf_dim * 8])
    # Batch normalize and relu
    h0 = tf.nn.relu(self.g_bn0(self.h0))

    h0 = conv_cond_concat(h0, yb)
    # Deconvolution layer 1
    self.h1, self.h1_w, self.h1_b = deconv2d(
        input_=h0,
        output_shape= [size, s_h8, s_w8, self.gf_dim*4],
        name='g_h1', with_w=True)
    # Batch normalize and relu
    h1 = tf.nn.relu(self.g_bn1(self.h1))

    h1 = conv_cond_concat(h1, yb)

    # Deconvolution layer 2
    h2, self.h2_w, self.h2_b = deconv2d(
        input_=h1, 
        output_shape=[size, s_h4, s_w4, self.gf_dim*2],
        name='g_h2',
        with_w=True)
    # Batch normalize and relu
    h2 = tf.nn.relu(self.g_bn2(h2))
    
    h2 = conv_cond_concat(h2, yb)

    # Deconvolution layer 3 
    h3, self.h3_w, self.h3_b = deconv2d(
        h2, [size, s_h2, s_w2, self.gf_dim*1], name='g_h3', with_w=True)
    # Batch normalize and relu
    h3 = tf.nn.relu(self.g_bn3(h3))

    h3 = conv_cond_concat(h3, yb)

    # Deconvolution layer 4 
    h4, self.h4_w, self.h4_b = deconv2d(
        input_=h3,
        output_shape=[size, s_h, s_w, self.c_dim],
        name='g_h4', with_w=True)
    
    # Return tanh, no batch normalization
    return self.gen_activation_function(h4)      
    

  def create_dcgan_generator(self,z, size, y=None):
    s_h, s_w = self.imsize, self.imsize

    # Define input sizes for convolutions
    s_h2, s_w2 = conv_out_size_same(s_h, 2), conv_out_size_same(s_w, 2)
    s_h4, s_w4 = conv_out_size_same(s_h2, 2), conv_out_size_same(s_w2, 2)
    s_h8, s_w8 = conv_out_size_same(s_h4, 2), conv_out_size_same(s_w4, 2)
    s_h16, s_w16 = conv_out_size_same(s_h8, 2), conv_out_size_same(s_w8, 2)

    # project `z` and reshape
    self.z_, self.h0_w, self.h0_b = linear(
        input_=z,
        output_size=self.gf_dim*8*s_h16*s_w16,
        scope='g_h0_lin', 
        with_w=True)

    self.h0 = tf.reshape(
        self.z_, [-1, s_h16, s_w16, self.gf_dim * 8])
    # Batch normalize and relu
    h0 = tf.nn.relu(self.g_bn0(self.h0))

    # Deconvolution layer 1
    self.h1, self.h1_w, self.h1_b = deconv2d(
        input_=h0,
        output_shape= [size, s_h8, s_w8, self.gf_dim*4],
        name='g_h1', with_w=True)
    # Batch normalize and relu
    h1 = tf.nn.relu(self.g_bn1(self.h1))

    # Deconvolution layer 2
    h2, self.h2_w, self.h2_b = deconv2d(
        input_=h1, 
        output_shape=[size, s_h4, s_w4, self.gf_dim*2],
        name='g_h2',
        with_w=True)
    # Batch normalize and relu

    h2 = tf.nn.relu(self.g_bn2(h2))
    
    # Deconvolution layer 3 
    h3, self.h3_w, self.h3_b = deconv2d(
        h2, [size, s_h2, s_w2, self.gf_dim*1], name='g_h3', with_w=True)
    # Batch normalize and relu
    h3 = tf.nn.relu(self.g_bn3(h3))

    # Deconvolution layer 4 
    h4, self.h4_w, self.h4_b = deconv2d(
        input_=h3,
        output_shape=[size, s_h, s_w, self.c_dim],
        name='g_h4', with_w=True)
    
    # Return tanh, no batch normalization
    return self.gen_activation_function(h4)

  def generator(self, z, y=None):
    return self.create_generator(z,self.batch_size,y)

  def sampler(self, z, y=None):
    return self.create_generator(z, self.sample_num * self.y_dim, y, reuse=True)

  def load_mnist(self):
    data_dir = os.path.join("./data", self.dataset_name)
    
    fd = open(os.path.join(data_dir,'train-images-idx3-ubyte'))
    loaded = np.fromfile(file=fd,dtype=np.uint8)
    trX = loaded[16:].reshape((60000,28,28,1)).astype(np.float)

    fd = open(os.path.join(data_dir,'train-labels-idx1-ubyte'))
    loaded = np.fromfile(file=fd,dtype=np.uint8)
    trY = loaded[8:].reshape((60000)).astype(np.float)

    fd = open(os.path.join(data_dir,'t10k-images-idx3-ubyte'))
    loaded = np.fromfile(file=fd,dtype=np.uint8)
    teX = loaded[16:].reshape((10000,28,28,1)).astype(np.float)

    fd = open(os.path.join(data_dir,'t10k-labels-idx1-ubyte'))
    loaded = np.fromfile(file=fd,dtype=np.uint8)
    teY = loaded[8:].reshape((10000)).astype(np.float)

    trY = np.asarray(trY)
    teY = np.asarray(teY)
    
    X = np.concatenate((trX, teX), axis=0)
    y = np.concatenate((trY, teY), axis=0).astype(np.int)
    
    seed = 547
    np.random.seed(seed)
    np.random.shuffle(X)
    np.random.seed(seed)
    np.random.shuffle(y)
    
    y_vec = np.zeros((len(y), self.y_dim), dtype=np.float)
    for i, label in enumerate(y):
      y_vec[i,y[i]] = 1.0
    
    return X/255.,y_vec

  def load_pokemon_y(self):
    y = [0]*802
    file_path = os.path.join('./data', self.dataset_name, "types.csv")
    f = open(file_path)
    reader = csv.reader(f,delimiter=",")
    for row in reader:
      # Skip first row
      if row[0] == "id":
        continue
      pid = int(row[0]) - 1
      typeid = row[3]
      y[pid] = int(typeid)
    onehot = np.zeros((len(y), self.y_dim), dtype=bool)
    for i in range(len(y)):
      onehot[i][y[i]] = 1
    return onehot
    

  @property
  def model_dir(self):
    return "{}_{}_{}_{}".format(
        self.dataset_name, self.batch_size,
        self.imsize, self.imsize)
      
  def save(self, checkpoint_dir, step):
    model_name = "DCGAN.model"
    checkpoint_dir = os.path.join(checkpoint_dir, self.model_dir)

    if not os.path.exists(checkpoint_dir):
      os.makedirs(checkpoint_dir)

    self.saver.save(self.sess,
            os.path.join(checkpoint_dir, model_name),
            global_step=step)

  def load(self, checkpoint_dir):
    import re
    print(" [*] Reading checkpoints...")
    checkpoint_dir = os.path.join(checkpoint_dir, self.model_dir)

    ckpt = tf.train.get_checkpoint_state(checkpoint_dir)
    if ckpt and ckpt.model_checkpoint_path:
      ckpt_name = os.path.basename(ckpt.model_checkpoint_path)
      self.saver.restore(self.sess, os.path.join(checkpoint_dir, ckpt_name))
      counter = int(next(re.finditer("(\d+)(?!.*\d)",ckpt_name)).group(0))
      print(" [*] Success to read {}".format(ckpt_name))
      return True, counter
    else:
      print(" [*] Failed to find a checkpoint")
      return False, 0

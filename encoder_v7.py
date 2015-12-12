#!/usr/bin/python
# -*- coding: utf-8 -*-


"""
bruce implement
"""
__author__ = "Wei Wang"
__email__ = "tskatom@vt.edu"

import sys
import os
import theano.tensor as T
import numpy as np
import theano
from util import dataset
import logging
import random
import cPickle
from theano.printing import Print as PP
np.set_printoptions(precision=4)

__process__ = "encoder_v6"

def train_encoder():
    logging.basicConfig(filename='./log/%s.log' % __process__, level=logging.INFO)

    # load data
    data_file = "./data/test_wikibased_dataset.pkl"
    print 1
    wiki_file = open("./data/polyglot-es.pkl")
    train_set, valid_set, test_set, word2id, pop2id, type2id = dataset.load_data(data_file)
    print 2
    # load the embedding
    wiki = cPickle.load(wiki_file)
    print 3
    wiki_file.close()
    rng = np.random.RandomState(10)

    embedding = wiki[1]
    embed_dm = embedding.shape[1]
    # sentenceLayer
    doc = T.lmatrix('doc') # num sentence * num words
    num_pop_class = 13
    
    
    embedding = theano.shared(value=np.asarray(rng.normal(size=embedding.shape), dtype=theano.config.floatX),
        borrow=True)
    filter_shape = [32, 1, embed_dm, 2]
    sen_layer_input = embedding[doc].dimshuffle(0, 'x', 2, 1)
    f_in = 1 * embed_dm * 2
    f_out = 64 * embed_dm * 2
    w_bound = np.sqrt(6./(f_in + f_out))
    w_bound = 0.5
    W0 = theano.shared(np.asarray(rng.normal(size=filter_shape),
        dtype=theano.config.floatX), borrow=True)
    b0 = theano.shared(np.zeros((filter_shape[0],), dtype=theano.config.floatX),
        borrow=True)

    sen_conv = T.nnet.conv.conv2d(PP('sen-layer-input')(sen_layer_input), W0, border_mode="valid")
    sen_conv_poolout = T.max(sen_conv, axis=3, keepdims=True)
    sen_conv_output = T.nnet.sigmoid(PP('sen_conv_pool_out')(sen_conv_poolout) + b0.dimshuffle('x', 0, 'x', 'x')).flatten(2)

    # construct the doc vector
    filter_shape1 = [32, 1, 32, 1]
    f_in = 1 * 64 * 1
    f_out = 64 * 64 * 1
    w_bound = np.sqrt(6./(f_in + f_out))
    w_bound = 0.5
    W1 = theano.shared(np.asarray(rng.normal(size=filter_shape1),
        dtype=theano.config.floatX), borrow=True)
    b1 = theano.shared(np.zeros((filter_shape1[0],), dtype=theano.config.floatX),
        borrow=True)
    doc_layer_input = sen_conv_output.dimshuffle('x','x',1,0)
    doc_conv = T.nnet.conv.conv2d(PP('doc_layer_input')(doc_layer_input), W1, border_mode="valid")
    doc_conv_poolout = T.max(doc_conv, axis=3, keepdims=True)
    doc_conv_out = T.nnet.sigmoid(PP('doc-conv-poolout')(doc_conv_poolout) + b1.dimshuffle('x', 0, 'x', 'x')).flatten(1)
    
    # construct hidden layer
    f_in = 32
    f_out = 5
    w_bound = np.sqrt(6./(f_in + f_out))
    w_bound = 0.5
    W2 = theano.shared(np.asarray(rng.normal(size=(f_in, f_out)),
        dtype=theano.config.floatX), borrow=True)
    b2 = theano.shared(np.zeros((f_out,), dtype=theano.config.floatX),
        borrow=True)
    hidd0_preact = T.dot(PP('doc_conv_out')(doc_conv_out), W2) + b2
    hidd0_output = T.nnet.sigmoid(hidd0_preact)

    # construct population task
    pop_y = T.iscalar('pop_y')
    f_in = 5
    f_out = num_pop_class
    w_bound = np.sqrt(6./(f_in + f_out))
    w_bound = 0.5
    W3 = theano.shared(np.asarray(rng.normal(size=(f_in, f_out)),
        dtype=theano.config.floatX), borrow=True)
    b3 = theano.shared(np.zeros(f_out, dtype=theano.config.floatX),
        borrow=True)
    pop_preact = T.dot(PP('Hidd0---->')(hidd0_output), W3) + b3
    pop_probs = T.nnet.softmax(PP('pop--preact')(pop_preact))
    pop_pred = T.argmax(pop_probs)
    pop_error = T.neq(pop_pred, pop_y)
    pop_cost = -1 * T.log(pop_probs[0, pop_y])

    # construct the model
    params = [W0, b0, W1, b1, W2, b2, W3, b3]
    grads = [T.grad(pop_cost, param) for param in params]
    updates = [(p, p - 0.01*g) for p, g in zip(params, grads)]

    train_func = theano.function([doc, pop_y], pop_cost, updates=updates)
    test_func= theano.function(inputs=[doc, pop_y], outputs=pop_error)

    # train the model
    ###############
    # TRAIN MODEL #
    ###############
    print "Start train model..., Load Data"
    # load dataset

    train_set_x, train_set_y = train_set
    train_set_pop_y, train_set_type_y, train_set_loc_y = train_set_y


    print "Data Loaded..."
    n_epochs = 1
    epoch = 0
    train_size = len(train_set_x[:3])
    done_looping = False
    random.seed(10)
    train_set_x, train_set_y = train_set
    train_set_pop_y, train_set_type_y, train_set_loc_y = train_set_y
    while epoch < n_epochs and not done_looping:
        # shuffle the train_set for each epoch
        indexs = range(train_size)
        epoch += 1
        for i, index in enumerate(indexs):
            x = np.asarray(train_set_x[index])
            pop_y = train_set_pop_y[index]
            cost_pop = test_func(x, pop_y)
            message = "Epoch %d index %d cost_pop %f" % (epoch, i, cost_pop)
            logging.info(message)

if __name__ == "__main__":
    train_encoder()
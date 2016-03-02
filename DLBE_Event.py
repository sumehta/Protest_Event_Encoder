#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Multi-Instance Deep Learning Model
"""

__author__ = "Wei Wang"
__email__ = "tskatom@vt.edu"

import sys
import os
import theano.tensor as T
import theano
import nn_layers as nn
from sklearn.metrics import precision_recall_fscore_support
import timeit
import argparse
import json
import cPickle
import numpy as np


def ReLU(x):
    return T.maximum(0.0, x)

def Tanh(x):
    return T.tanh(x)

def keep_max(input, theta, k):
    sig_input = T.nnet.sigmoid(T.dot(input, theta))
    sig_input = sig_input * sent_mask

    if k== 0:
        result = input * T.addbroadcast(sig_input, 3)
        return result

    sort_idx = T.argsort(sig_input, axis=2)
    k_max_ids = sort_idx[:,:,-k:,:]
    dim0, dim1, dim2, dim3 = k_max_ids.shape
    batchids = T.repeat(T.arange(dim0), dim1*dim2*dim3)
    mapids = T.repeat(T.arange(dim1), dim2*dim3).reshape((1, dim2*dim3))
    mapids = T.repeat(mapids, dim0, axis=0).flatten()
    rowids = k_max_ids.flatten()
    colids = T.arange(dim3).reshape((1, dim3))
    colids = T.repeat(colids, dim0*dim1*dim2, axis=0).flatten()
    sig_mask = T.zeros_like(sig_input)
    choosed = sig_input[batchids, mapids, rowids, colids]
    sig_mask = T.set_subtensor(sig_mask[batchids, mapids, rowids, colids], 1)
    input_mask = sig_mask * sig_input
    result = input * T.addbroadcast(input_mask, 3)
    return result, sig_input

class GICF(object):
    def __init__(self, options):
        self.options = options
        self.params = []

    def run_experiment(self, dataset, word_embedding, exp_name):
        
        # load parameters
        num_maps_word = self.options["num_maps_word"]
        drop_rate_word = self.options["drop_rate_word"]
        drop_rate_sentence = self.options["drop_rate_sentence"]
        word_window = self.options["word_window"]
        word_dim = self.options["word_dim"]
        k_max_word = self.options["k_max_word"]
        batch_size = self.options["batch_size"]
        rho = self.options["rho"]
        epsilon = self.options["epsilon"]
        norm_lim = self.options["norm_lim"]
        max_iteration = self.options["max_iteration"]
        k = self.options["k_max"]

        sentence_len = len(dataset[0][0][0][0])
        sentence_num = len(dataset[0][0][0])
        
        # define the parameters
        x = T.tensor3("x")
        y = T.ivector("y")
        rng = np.random.RandomState(1234)
        
        words = theano.shared(value=np.asarray(word_embedding,
            dtype=theano.config.floatX),
            name="embedding", borrow=True)
        zero_vector_tensor = T.vector() 
        zero_vec = np.zeros(word_dim, dtype=theano.config.floatX)
        set_zero = theano.function([zero_vector_tensor], updates=[(words, T.set_subtensor(words[0,:], zero_vector_tensor))])

        x_emb = words[T.cast(x.flatten(), dtype="int32")].reshape((x.shape[0]*x.shape[1], 1, x.shape[2], words.shape[1]))

        dropout_x_emb = nn.dropout_from_layer(rng, x_emb, drop_rate_word)

        # compute convolution on words layer
        word_filter_shape = (num_maps_word, 1, word_window, word_dim)
        word_pool_size = (sentence_len - word_window + 1, 1)
        dropout_word_conv = nn.ConvPoolLayer(rng, 
                input=dropout_x_emb,
                input_shape=None,
                filter_shape=word_filter_shape,
                pool_size=word_pool_size,
                activation=Tanh,
                k=k_max_word)
        sent_vec_dim = num_maps_word*k_max_word
        dropout_sent_vec = dropout_word_conv.output.reshape((x.shape[0] * x.shape[1], sent_vec_dim))

        word_conv = nn.ConvPoolLayer(rng, 
                input=dropout_x_emb*(1 - drop_rate_word),
                input_shape=None,
                filter_shape=word_filter_shape,
                pool_size=word_pool_size,
                activation=Tanh,
                k=k_max_word,
                W=dropout_word_conv.W,
                b=dropout_word_conv.b)
        sent_vec = word_conv.output.reshape((x.shape[0] * x.shape[1], sent_vec_dim))
        
        theta_value = np.random.random((sent_vec_dim,1))
        theta = shared(value=np.asarray(theta_value, dtype=theano.config.floatX), name="theta", borrow=True)
        weighted_drop_sent_vec, weighted_sen_score = keep_max(dropout_sent_vec.reshape((x.shape[0], 1, x.shape[1], sent_vec_dim)), theta, k)
        drop_doc_vec = T.sum(weighted_drop_sent_vec, axis=2).flatten(2)
        
        weighted_sent_vec, sen_score = keep_max(sent_vec.reshape((x.shape[0], 1, x.shape[1], sent_vec_dim)), theta, k)
        doc_vec = T.sum(weighted_sent_vec, axis=2).flatten(2)
        # we need to constrain the number of positive sentences in positive
        

        
        # collect parameters
        self.params.append(words)
        self.params += dropout_word_conv.params
        self.params.append(sen_W)
        self.params.append(sen_b)
        
        grad_updates = nn.sgd_updates_adadelta(self.params,
                drop_cost,
                rho,
                epsilon,
                norm_lim)

        # construct the dataset
        train_x, train_y = nn.shared_dataset(dataset[0])
        test_x, test_y = nn.shared_dataset(dataset[1])
        test_cpu_y = dataset[1][1]

        n_train_batches = int(np.ceil(1.0 * len(dataset[0][0]) / batch_size))
        n_test_batches = int(np.ceil(1.0 * len(dataset[1][0]) / batch_size))

        # construt the model
        index = T.iscalar()
        train_func = theano.function([index], [drop_cost, drop_bag_cost, drop_sent_cost, penal_cost], updates=grad_updates,
                givens={
                    x: train_x[index*batch_size:(index+1)*batch_size],
                    y: train_y[index*batch_size:(index+1)*batch_size]
                    })

        test_func = theano.function([index], doc_preds,
                givens={
                    x:test_x[index*batch_size:(index+1)*batch_size]
                    })

        get_train_sent_prob = theano.function([index], sent_prob,
                givens={
                    x:train_x[index*batch_size:(index+1)*batch_size]
                    })

        get_test_sent_prob = theano.function([index], sent_prob,
                givens={
                    x:test_x[index*batch_size:(index+1)*batch_size]
                    })

        epoch = 0
        best_score = 0
        raw_train_x = dataset[0][0]
        raw_test_x = dataset[1][0]
        # get the sentence number for each document
        number_train_sens = []
        number_test_sens = []


        log_file = open("./log/%s.log" % exp_name, 'w')

        while epoch <= max_iteration:
            start_time = timeit.default_timer()
            epoch += 1
            costs = []

            for minibatch_index in np.random.permutation(range(n_train_batches)):
                cost_epoch = train_func(minibatch_index)
                costs.append(cost_epoch)
                set_zero(zero_vec)

            total_train_cost, train_bag_cost, train_sent_cost, train_penal_cost = zip(*costs)
            print "Iteration %d, total_cost %f bag_cost %f sent_cost %f penal_cost %f\n" %  (epoch, np.mean(total_train_cost), np.mean(train_bag_cost), np.mean(train_sent_cost), np.mean(train_penal_cost))

            if epoch % 5 == 0:
                test_preds = []
                for i in xrange(n_test_batches):
                    test_y_pred = test_func(i)
                    test_preds.append(test_y_pred)
                test_preds = np.concatenate(test_preds)
                test_score = 1 - np.mean(np.not_equal(test_cpu_y, test_preds))

                precision, recall, beta, support = precision_recall_fscore_support(test_cpu_y, test_preds, pos_label=1)

                if test_score > best_score:
                    best_score = test_score
                    # save the sentence vectors
                    train_sens = [get_train_sent_prob(i) for i in range(n_train_batches)]
                    test_sens = [get_test_sent_prob(i) for i in range(n_test_batches)]

                    train_sens = np.concatenate(train_sens, axis=0)
                    test_sens = np.concatenate(test_sens, axis=0)

                    out_train_sent_file = "./results/%s_train_sent.vec" % exp_name
                    out_test_sent_file = "./results/%s_test_sent.vec" % exp_name

                    with open(out_train_sent_file, 'w') as train_f, open(out_test_sent_file, 'w') as test_f:
                        cPickle.dump(train_sens, train_f)
                        cPickle.dump(test_sens, test_f)
                    print "Get best performace at %d iteration %f" % (epoch, test_score)
                    log_file.write("Get best performance at %d iteration %f \n" % (epoch, test_score))

                end_time = timeit.default_timer()
                print "Iteration %d , precision, recall, support" % epoch, precision, recall, support
                log_file.write("Iteration %d, neg precision %f, pos precision %f, neg recall %f pos recall %f , total_cost %f bag_cost %f sent_cost %f penal_cost %f\n" % (epoch, precision[0], precision[1], recall[0], recall[1], np.mean(total_train_cost), np.mean(train_bag_cost), np.mean(train_sent_cost), np.mean(train_penal_cost)))
                print "Using time %f m" % ((end_time -start_time)/60.)
                log_file.write("Uing time %f m\n" % ((end_time - start_time)/60.))
            end_time = timeit.default_timer()
            print "Iteration %d Using time %f m" % ( epoch, (end_time -start_time)/60.)
            log_file.write("Uing time %f m\n" % ((end_time - start_time)/60.))
            log_file.flush()

        log_file.close()
def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--option", type=str, help="the configuration file")
    ap.add_argument("--prefix", type=str, help="The prefix for experiment")
    ap.add_argument("--sufix", type=str, 
            default="event_cat", help="the sufix for experiment")
    ap.add_argument("--data_type", type=str, default="json", 
            help="the data type for text file: json or str")
    ap.add_argument("--event_fn", type=str, help="the event category dictionary file")
    ap.add_argument("--word2vec", type=str, help="word2vec file")
    ap.add_argument("--exp_name", type=str, help="the name of the experiment")
    return ap.parse_args()


def main():
    args = parse_args()
    option = json.load(open(args.option))
    prefix = args.prefix
    sufix = args.sufix
    data_type = args.data_type
    event_fn = args.event_fn
    word2vec_file = args.word2vec
    exp_name = args.exp_name

    max_sens = option["max_sens"]
    max_words = option["max_words"]
    padding = option["padding"]

    class2id = {k.strip():i for i,k in enumerate(open(event_fn))}
    
    dataset = nn.load_event_dataset(prefix, sufix)
    wf = open(word2vec_file)
    embedding = cPickle.load(wf)
    word2id = cPickle.load(wf)

    digit_dataset = nn.transform_event_dataset(dataset, word2id, class2id, data_type, max_sens, max_words, padding)

    model = GICF(option)
    model.run_experiment(digit_dataset, embedding, exp_name)


if __name__ == "__main__":
    main()

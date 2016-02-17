#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Convolution Neural Network for Event Encoding
"""

__author__ = "Wei Wang"
__email__ = "tskatom@vt.edu"

import sys
import os
import theano
from theano import function, shared
import theano.tensor as T
import numpy as np
import cPickle
import json
import argparse
import nn_layers as nn
import logging
import timeit
from collections import OrderedDict
import re
from nltk import word_tokenize

#from CNN_Sen import split_doc2sen

#theano.config.profile = True
#theano.config.profile_memory = True
#theano.config.optimizer = 'fast_run'

def ReLU(x):
    return T.maximum(0.0, x)

def as_floatX(variable):
    if isinstance(variable, float):
        return np.cast[theano.config.floatX](variable)
    if isinstance(variable, np.ndarray):
        return np.cast[theano.config.floatX](variable)
    return theano.tensor.cast(variable, theano.config.floatX)

def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument('--prefix', type=str,
            help="the prefix for input data such as spanish_protest")
    ap.add_argument('--word2vec', type=str,
            help="word vector pickle file")
    ap.add_argument('--sufix_pop', type=str,
            help="the sufix for the target file")
    ap.add_argument('--sufix_type', type=str,
            help="the sufix for the target file")
    ap.add_argument('--dict_pop_fn', type=str,
            help='population class dictionary')
    ap.add_argument('--dict_type_fn', type=str,
            help='event type class dictionary')
    ap.add_argument('--max_len', type=int,
            help='the max length for doc used for mini-batch')
    ap.add_argument("--padding", type=int,
            help="the number of padding used to add begin and end doc")
    ap.add_argument("--exp_name", type=str,
            help="experiment name")
    ap.add_argument("--static", action="store_true", 
            help="whether update word2vec")
    ap.add_argument("--max_iter", type=int,
            help="max iterations")
    ap.add_argument("--batch_size", type=int)
    ap.add_argument("--log_fn", type=str,
            help="log filename")
    ap.add_argument("--perf_fn", type=str,
            help="folder to store predictions")
    ap.add_argument("--param_fn", type=str,
            help="sepcific local params")
    ap.add_argument("--max_sens", type=int, default=40,
            help="the max number of sens in a document")
    ap.add_argument("--max_words", type=int, default=80,
            help="the max number of sentences for each sentence")
    ap.add_argument("--top_k", type=int, default=0,
            help="the maximum of sentence to choose")
    ap.add_argument("--print_freq", type=int, default=5,
            help="the frequency of print frequency") 
    ap.add_argument("--data_type", type=str, help="data input format")
    ap.add_argument("--flag", type=str, help="prediction type")
    return ap.parse_args()

def load_dataset(prefix, sufix_1, sufix_2):
    """Load the train/valid/test set
        prefix eg: ../data/spanish_protest
        sufix eg: pop_cat
    """
    dataset = []
    for group in ["train", "test"]:
        x_fn = "%s_%s.txt.tok" % (prefix, group)
        y1_fn = "%s_%s.%s" % (prefix, group, sufix_1)
        y2_fn = "%s_%s.%s" % (prefix, group, sufix_2)
        xs = [l.strip() for l in open(x_fn)]
        y1s = [l.strip() for l in open(y1_fn)]
        y2s = [l.strip() for l in open(y2_fn)]
        dataset.append((xs, y1s, y2s))
        print "Load %d %s records" % (len(y1s), group)
    return dataset

def split_doc2sen(doc, word2id, data_type, max_sens, max_words, padding):
    if data_type == "str":
        sens = re.split("\.|\?|\|", doc.lower())
        sens = [sen for sen in sens if len(sen.strip().split(" ")) > 5]
    elif data_type == "json":
        sens = [sen.lower() for sen in json.loads(doc)]
        
    pad = padding
    sens_pad = []
    word_count = {}
    doc_sids = []
    sent_mask = []
    for j, sen in enumerate(sens[:max_sens]):
        sen_ids = [0] * pad
        sid = [j + 1] * pad
        #tokens = sen.strip().split(" ")
        tokens = word_tokenize(sen)
        for w in tokens[:max_words]:
            sen_ids.append(word2id.get(w.encode('utf-8'), 1))
            sid.append(j + 1)
        num_suff = max(0, max_words - len(tokens)) + pad
        sen_ids += [0] * num_suff
        sid += [j+1] * num_suff
        sens_pad.append(sen_ids)
        doc_sids.append(sid)
        sent_mask.append(1)
    # add more padding sentence
    num_suff = max(0, max_sens - len(sens))
    for i in range(0, num_suff):
        sid = [0] * len(sens_pad[0])
        sen_ids = [0] * len(sens_pad[0])
        sens_pad.append(sen_ids)
        doc_sids.append(sid)
        sent_mask.append(0)

    # compute the frequency
    for sen in sens_pad:
        for wid in sen:
            if wid not in word_count:
                word_count[wid] = 0
            word_count[wid] += 1
    doc_freqs = []
    for sen in sens_pad:
        doc_freq = []
        for wid in sen:
            if wid == 0:
                doc_freq.append(0)
            else:
                doc_freq.append(word_count[wid] if word_count[wid] <= 20 else 20)
        doc_freqs.append(doc_freq)

    return sens_pad, doc_freqs, doc_sids, sent_mask

def transform_dataset(dataset, word2id, class2id, data_type, max_sens=40, max_words=80, padding=5):
    """Transform the dataset into digits"""
    train_set, test_set = dataset
    train_doc, train_pop_class, train_type_class = train_set
    test_doc, test_pop_class, test_type_class = test_set
    
    train_doc_ids, train_doc_freqs, train_doc_sids, train_sent_mask = zip(*[split_doc2sen(doc, word2id, data_type, max_sens, max_words, padding) for doc in train_doc])
    test_doc_ids, test_doc_freqs, test_doc_sids, test_sent_mask = zip(*[split_doc2sen(doc, word2id, data_type, max_sens, max_words, padding) for doc in test_doc])

    train_pop_y = [class2id["pop"][c] for c in train_pop_class]
    test_pop_y = [class2id["pop"][c] for c in test_pop_class]
    
    train_type_y = [class2id["type"][c] for c in train_type_class]
    test_type_y = [class2id["type"][c] for c in test_type_class]

    return [(train_doc_ids, train_doc_freqs, train_doc_sids, train_sent_mask, train_pop_y, train_type_y), (test_doc_ids, test_doc_freqs, test_doc_sids, test_sent_mask, test_pop_y, test_type_y)]


def sgd_updates_adadelta(params, cost, rho=0.95, epsilon=1e-6,
        norm_lim=9, word_vec_name='embedding'):
    updates = OrderedDict({})
    exp_sqr_grads = OrderedDict({})
    exp_sqr_ups = OrderedDict({})
    gparams = [] 
    for param in params:
        empty = np.zeros_like(param.get_value())
        exp_sqr_grads[param] = theano.shared(value=as_floatX(empty),name="exp_grad_%s" % param.name)
        gp = T.grad(cost, param)
        exp_sqr_ups[param] = theano.shared(value=as_floatX(empty), name="exp_grad_%s" % param.name)
        gparams.append(gp)

    for param, gp in zip(params, gparams):
        exp_sg = exp_sqr_grads[param] 
        exp_su = exp_sqr_ups[param]
        up_exp_sg = rho * exp_sg + (1 - rho) * T.sqr(gp)
        updates[exp_sg] = up_exp_sg
        step =  -(T.sqrt(exp_su + epsilon) / T.sqrt(up_exp_sg + epsilon)) * gp
        updates[exp_su] = rho * exp_su + (1 - rho) * T.sqr(step)
        stepped_param = param + step
        
        if (param.get_value(borrow=True).ndim == 2) and (param.name!='embedding'):
            col_norms = T.sqrt(T.sum(T.sqr(stepped_param), axis=0)) 
            desired_norms = T.clip(col_norms, 0, T.sqrt(norm_lim)) 
            scale = desired_norms / (1e-7 + col_norms)
            updates[param] = stepped_param * scale
        else:
            updates[param] = stepped_param
    return updates


def keep_max(input, theta, k, sent_mask):
    sig_input = T.nnet.sigmoid(T.dot(input, theta))
    sent_mask = sent_mask.dimshuffle(0, 'x', 1, 'x')
    sig_input = sig_input * sent_mask
    #sig_input = T.dot(input, theta)
    if k == 0:
        result = input * T.addbroadcast(sig_input, 3)
        return result, sig_input

    # get the sorted idx
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


def run_cnn(exp_name,
        dataset, embedding,
        log_fn, perf_fn,
        k=0,
        emb_dm=100,
        batch_size=100,
        filter_hs=[1, 2, 3],
        hidden_units=[200, 100, 11],
        dropout_rate=0.5,
        shuffle_batch=True,
        n_epochs=300,
        lr_decay=0.95,
        activation=ReLU,
        sqr_norm_lim=9,
        non_static=True,
        print_freq=5,
        flag="pop"
        ):
    """
    Train and Evaluate CNN event encoder model
    :dataset: list containing three elements[(train_x, train_y), 
            (valid_x, valid_y), (test_x, test_y)]
    :embedding: word embedding with shape (|V| * emb_dm)
    :filter_hs: filter height for each paralle cnn layer
    :dropout_rate: dropout rate for full connected layers
    :n_epochs: the max number of iterations
    
    """
    start_time = timeit.default_timer()
    rng = np.random.RandomState(1234)
   
    input_height = len(dataset[0][0][0][0])
    num_sens = len(dataset[0][0][0])
    print "--input height ", input_height 
    num_maps = hidden_units[0]

    ###################
    # start snippet 1 #
    ###################
    print "start to construct the model ...."
    word_x = T.tensor3("word_x")
    freq_x = T.tensor3("freq_x")
    pos_x = T.tensor3("pos_x")
    sent_x = T.matrix("sent_x")
    y = T.ivector("y")

    words = shared(value=np.asarray(embedding,
        dtype=theano.config.floatX), 
        name="embedding", borrow=True)

    sym_dim = 20
    # the frequency embedding is 21 * sym_dim matrix
    freq_val = np.random.random((21, sym_dim)).astype(theano.config.floatX)
    freqs = shared(value=freq_val, borrow=True, name="freqs")

    pos_val = np.random.random((21, sym_dim)).astype(theano.config.floatX)
    poss = shared(value=pos_val, borrow=True, name="poss")

    # define function to keep padding vector as zero
    zero_vector_tensor = T.vector()
    zero_vec = np.zeros(emb_dm, dtype=theano.config.floatX)
    set_zero = function([zero_vector_tensor],
            updates=[(words, T.set_subtensor(words[0,:], zero_vector_tensor))])

    freq_zero_tensor = T.vector()
    freq_zero_vec = np.zeros(sym_dim, dtype=theano.config.floatX)
    freq_set_zero = function([freq_zero_tensor], updates=[(freqs, T.set_subtensor(freqs[0,:], freq_zero_tensor))])

    pos_zero_tensor = T.vector()
    pos_zero_vec = np.zeros(sym_dim, dtype=theano.config.floatX)
    pos_set_zero = function([pos_zero_tensor], updates=[(poss, T.set_subtensor(poss[0,:], pos_zero_tensor))])
    
    word_x_emb = words[T.cast(word_x.flatten(), dtype="int32")].reshape((word_x.shape[0] * word_x.shape[1], 1, word_x.shape[2], emb_dm))
    freq_x_emb = freqs[T.cast(freq_x.flatten(), dtype="int32")].reshape((freq_x.shape[0] * freq_x.shape[1], 1, freq_x.shape[2], sym_dim))
    pos_x_emb = poss[T.cast(pos_x.flatten(), dtype="int32")].reshape((pos_x.shape[0]*pos_x.shape[1], 1, pos_x.shape[2], sym_dim))
    
    """
    layer0_input = words[T.cast(x.flatten(), dtype="int32")].reshape((
        x.shape[0] * x.shape[1], 1, x.shape[2], emb_dm
        ))
    """
    layer0_input = T.concatenate([word_x_emb, freq_x_emb, pos_x_emb], axis=3)
    conv_layers = []
    layer1_inputs = []

    for i in xrange(len(filter_hs)):
        filter_shape = (num_maps, 1, filter_hs[i], emb_dm + sym_dim + sym_dim)
        pool_size = (input_height - filter_hs[i] + 1, 1)
        conv_layer = nn.ConvPoolLayer(rng, input=layer0_input, 
                input_shape=None,
                filter_shape=filter_shape,
                pool_size=pool_size, activation=activation)
        sen_vecs = conv_layer.output.reshape((word_x.shape[0], 1, word_x.shape[1], num_maps))
        # construct multi-layer sentence vectors

        conv_layers.append(conv_layer)
        layer1_inputs.append(sen_vecs)
    
    sen_vec = T.concatenate(layer1_inputs, 3)
    # score the sentences
    theta_value = np.random.random((len(filter_hs) * num_maps, 1))
    theta = shared(value=np.asarray(theta_value, dtype=theano.config.floatX),
            name="theta", borrow=True)
    weighted_sen_vecs, sen_score = keep_max(sen_vec, theta, k, sent_x)
    sen_score_cost = T.mean(T.sum(sen_score, axis=2).flatten(1))
    doc_vec = T.sum(weighted_sen_vecs, axis=2)
    layer1_input = doc_vec.flatten(2) 
    final_sen_score = sen_score.flatten(2)

    ##############
    # classifier pop#
    ##############
    params = []
    for conv_layer in conv_layers:
        params += conv_layer.params
    params.append(theta)
    params.append(words)
    params.append(freqs)
    params.append(poss)
    
    gamma = as_floatX(0.0005)
    beta1 = as_floatX(0.000)
    total_cost = gamma * sen_score_cost 
    total_dropout_cost = gamma * sen_score_cost


    print "Construct classifier ...."
    hidden_units[0] = num_maps * len(filter_hs)
    model = nn.MLPDropout(rng,
            input=layer1_input,
            layer_sizes=hidden_units,
            dropout_rates=[dropout_rate],
            activations=[activation])

    params += model.params

    cost = model.negative_log_likelihood(y)
    dropout_cost = model.dropout_negative_log_likelihood(y)

    total_cost += cost + beta1 * model.L1
    total_dropout_cost += dropout_cost + beta1 * model.L1



    # using adagrad
    lr = 0.01
    """
    total_grad_updates = nn.optimizer(total_dropout_cost,
            params,
            lr,
            method="adadelta"
            )
    """
    total_grad_updates = sgd_updates_adadelta(params, 
            total_dropout_cost,
            lr_decay,
            1e-6,
            sqr_norm_lim)
   

    #####################
    # Construct Dataset #
    #####################
    print "Copy data to GPU and constrct train/valid/test func"
    
    train_word_x, train_freq_x, train_pos_x, train_sent_x, train_pop_y, train_type_y = shared_dataset(dataset[0])
    test_word_x, test_freq_x, test_pos_x, test_sent_x, test_pop_y, test_type_y = shared_dataset(dataset[1])

    if flag == "pop":
        train_y = train_pop_y
    elif flag == "type":
        train_y = train_type_y

    n_train_batches = int(np.ceil(1.0 * len(dataset[0][0]) / batch_size))
    n_test_batches = int(np.ceil(1.0 * len(dataset[1][0]) / batch_size))

    #####################
    # Train model func #
    #####################
    index = T.iscalar()
    train_func = function([index], total_cost, updates=total_grad_updates,
            givens={
                word_x: train_word_x[index*batch_size:(index+1)*batch_size],
                freq_x: train_freq_x[index*batch_size:(index+1)*batch_size],
                pos_x: train_pos_x[index*batch_size:(index+1)*batch_size],
                sent_x:train_sent_x[index*batch_size:(index+1)*batch_size],
                y: train_y[index*batch_size:(index+1)*batch_size],
                })
    
    test_pred = function([index], model.preds,
            givens={
                word_x:test_word_x[index*batch_size:(index+1)*batch_size],
                freq_x:test_freq_x[index*batch_size:(index+1)*batch_size],
                pos_x:test_pos_x[index*batch_size:(index+1)*batch_size],
                sent_x:test_sent_x[index*batch_size:(index+1)*batch_size]
                })
    
    test_sentence_est = function([index], final_sen_score,
            givens={
                word_x: test_word_x[index*batch_size:(index+1)*batch_size],
                freq_x: test_freq_x[index*batch_size:(index+1)*batch_size],
                pos_x: test_pos_x[index*batch_size:(index+1)*batch_size],
                sent_x:test_sent_x[index*batch_size:(index+1)*batch_size]
                })
    
    train_sentence_est = function([index], final_sen_score,
            givens={
                word_x: train_word_x[index*batch_size:(index+1)*batch_size],
                freq_x: train_freq_x[index*batch_size:(index+1)*batch_size],
                pos_x: train_pos_x[index*batch_size:(index+1)*batch_size],
                sent_x:train_sent_x[index*batch_size:(index+1)*batch_size]
                })


    # apply early stop strategy
    patience = 100
    patience_increase = 2
    improvement_threshold = 1.005
    
    n_test = len(dataset[1][0])

    epoch = 0
    best_params = None
    best_validation_score = 0.
    test_perf = 0

    done_loop = False
    
    log_file = open(log_fn, 'w')

    print "Start to train the model....."
    cpu_tst_pop_y = np.asarray(dataset[1][4])
    cpu_tst_type_y = np.asarray(dataset[1][5])
    if flag == "pop":
        cpu_tst_y = cpu_tst_pop_y
    elif flag == "type":
        cpu_tst_y = cpu_tst_type_y

    def compute_score(true_list, pred_list):
        mat = np.equal(true_list, pred_list)
        score = np.mean(mat)
        return score
    
    total_score = 0.0
    while (epoch < n_epochs) and not done_loop:
        start_time = timeit.default_timer()
        epoch += 1
        costs = []
        for minibatch_index in np.random.permutation(range(n_train_batches)):
            cost_epoch = train_func(minibatch_index)
            costs.append(cost_epoch)
            set_zero(zero_vec)
            freq_set_zero(freq_zero_vec)
            pos_set_zero(pos_zero_vec)
        

        if epoch % print_freq == 0:
            # do test
            test_preds = np.concatenate([test_pred(i) for i in xrange(n_test_batches)])
            test_score = compute_score(cpu_tst_y, test_preds)
            with open(os.path.join(perf_fn, "%s_%d.pred" % (exp_name, epoch)), 'w') as epf:
                for p in test_preds:
                    epf.write("%d\n" % int(p))


            message = "Epoch %d test perf %f, with train cost %f" % (epoch, test_score, np.mean(costs))

            print message
            log_file.write(message + "\n")
            log_file.flush()

            if (test_score > total_score) or (epoch % 15 == 0):
                total_score = test_score
                # save the sentence score
                test_sen_score = [test_sentence_est(i) for i in xrange(n_test_batches)]
                score_file = "./results/%s_%d_test.score" % (exp_name, epoch)
                with open(score_file, "wb") as sm:
                    cPickle.dump(test_sen_score, sm)
                
                #train_sen_score = [train_sentence_est(i) for i in xrange(n_train_batches)]
                #score_file = "./results/%s_%d_train.score" % (exp_name, epoch)
                #with open(score_file, "wb") as sm:
                    #cPickle.dump(train_sen_score, sm)

        end_time = timeit.default_timer()
        print "Finish one iteration using %f m" % ((end_time - start_time)/60.)

    log_file.flush()
    log_file.close()


def shared_dataset(data_xyz, borrow=True):
    data_word_x, data_freq_x, data_pos_x, data_sent_x, data_y, data_z = data_xyz
    shared_word_x = theano.shared(np.asarray(data_word_x,
        dtype=theano.config.floatX), borrow=borrow)

    shared_freq_x = theano.shared(np.asarray(data_freq_x,
        dtype=theano.config.floatX), borrow=borrow)

    shared_pos_x = theano.shared(np.asarray(data_pos_x,
        dtype=theano.config.floatX), borrow=borrow)

    shared_sent_x = theano.shared(np.asarray(data_sent_x, dtype=theano.config.floatX),
            borrow=True)

    shared_y = theano.shared(np.asarray(data_y,
        dtype=theano.config.floatX), borrow=borrow)
    
    shared_z = theano.shared(np.asarray(data_z,
        dtype=theano.config.floatX), borrow=borrow)

    return shared_word_x, shared_freq_x, shared_pos_x, shared_sent_x, T.cast(shared_y, 'int32'), T.cast(shared_z, 'int32')


def main():
    args = parse_args()
    prefix = args.prefix
    word2vec_file = args.word2vec
    sufix_pop = args.sufix_pop
    sufix_type = args.sufix_type
    expe_name = args.exp_name
    batch_size = args.batch_size
    log_fn = args.log_fn
    perf_fn = args.perf_fn
    top_k = args.top_k
    print_freq = args.print_freq
    data_type = args.data_type
    flag = args.flag

    # load the dataset
    print 'Start loading the dataset ...'
    dataset = load_dataset(prefix, sufix_pop, sufix_type)
    wf = open(word2vec_file)
    embedding = cPickle.load(wf)
    word2id = cPickle.load(wf)

    class2id = {}
    dict_pop_file = args.dict_pop_fn
    class2id["pop"] = {k.strip(): i for i, k in enumerate(open(dict_pop_file))}
    
    dict_type_file = args.dict_type_fn
    class2id["type"] = {k.strip(): i for i, k in enumerate(open(dict_type_file))}
    
    # transform doc to dig list and padding docs
    print 'Start to transform doc to digits'
    max_sens = args.max_sens
    max_words = args.max_words
    padding = args.padding
    digit_dataset = transform_dataset(dataset, word2id, class2id, data_type, max_sens, max_words, padding)

    non_static = not args.static
    exp_name = args.exp_name
    n_epochs = args.max_iter

    # load local parameters
    loc_params = json.load(open(args.param_fn))
    filter_hs = loc_params["filter_hs"]
    hidden_units = loc_params["hidden_units"]

    run_cnn(exp_name, digit_dataset, embedding,
            log_fn, perf_fn,
            k=top_k,
            emb_dm=embedding.shape[1],
            batch_size=batch_size,
            filter_hs=filter_hs,
            hidden_units=hidden_units,
            dropout_rate=0.5,
            shuffle_batch=True,
            n_epochs=n_epochs,
            lr_decay=0.95,
            activation=ReLU,
            sqr_norm_lim=3,
            non_static=non_static,
            print_freq=print_freq,
            flag=flag
            )
     
    
if __name__ == "__main__":
    main()

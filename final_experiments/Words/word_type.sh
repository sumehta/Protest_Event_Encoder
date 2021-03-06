#!/bin/bash

# preprocess the data 

# generate vocab from training dataset
prep_exe=../util/prepText
text_tool=../util/tools.py
model_exe=../CNN_no_validation.py
options="LowerCase UTF8 RemoveNumbers"
max_num=100000
min_word_count=1
word_dm=200

echo Generating vocabulary for training data ... \n
vocab_fn=data/spanish_protest.trn-${max_num}.vocab
$prep_exe gen_vocab input_fn=./data/tokens.lst vocab_fn=$vocab_fn max_vocab_size=$max_num \
    min_word_count=$min_word_count $options WriteCount

echo Construct two set of vocabulary embedding: ramdom and pretrained \n
vec_trained_fn=./data/trained_w2v_${word_dm}.pkl
vec_random_fn=./data/random_w2v_${word_dm}.pkl
pretrained_fn=../data/${word_dm}d_vectors.txt
python $text_tool --task gen_emb --vocab_fn $vocab_fn --vec_random_fn $vec_random_fn --vec_trained_fn $vec_trained_fn --pretrained_fn $pretrained_fn --emb_dm $word_dm

echo Start Training the model
exp_name=word_type_d75
log_fn=./log/${exp_name}.log
perf_fn=./results/
param_fn=./type_param.json
python $model_exe --prefix ../data/single_label/spanish_protest --sufix type_cat --word2vec $vec_trained_fn --dict_fn ../data/type_cat.dic --max_len 2000 --padding 3 --exp_name $exp_name --max_iter 100 --batch_size 100 --log_fn $log_fn --perf_fn $perf_fn --param_fn $param_fn



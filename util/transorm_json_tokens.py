#!/usr/bin/python
# -*- coding: utf-8 -*-

__author__ = "Wei Wang"
__email__ = "tskatom@vt.edu"

import sys
import os
import json
from nltk import word_tokenize

infile = "/home/ubuntu/workspace/Protest_Event_Encoder/data/new_single_label/spanish_protest.txt.tok"
outfile = "/home/ubuntu/workspace/Protest_Event_Encoder/data/new_single_label/spanish_protest.tokens"

infile = sys.argv[1]
outfile = sys.argv[2]


with open(infile) as in_file, open(outfile, 'w') as otf:
    for line in in_file:
        sens = json.loads(line)
        tokens = [token for sen in sens for token in word_tokenize(sen.lower())]
        doc = u' '.join(tokens)
        otf.write(doc.encode('utf-8') + "\n")
        



if __name__ == "__main__":
    pass

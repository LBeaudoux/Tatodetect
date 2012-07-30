#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#Tatoeba Project, free collaborative creation of multilingual corpuses project
#Copyright (C) 2012 Allan SIMON <allan.simon@supinfo.com>
#
#This program is free software: you can redistribute it and/or modify
#it under the terms of the GNU Affero General Public License as published by
#the Free Software Foundation, either version 3 of the License, or
#(at your option) any later version.
#
#This program is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU Affero General Public License for more details.
#
#You should have received a copy of the GNU Affero General Public License
#along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#
#@category Tatodetect
#@package  Tools
#@author   Allan SIMON <allan.simon@supinfo.com>
#@license  Affero General Public License
#@link     http://tatoeba.org
#

import codecs
import os
import sqlite3
from collections import defaultdict
import urllib.request

# where to download the file
URL_DL_FILES = "http://tatoeba.org/app/webroot/files/downloads/"
# name of the file to download
SENTENCES_DETAILED = "sentences_detailed.csv"
#where the database will be saved
DB_DIR = "../data/"

# languages that don't use an alphabet
# we put them apart as they are likely to have a lot of different
# ngrams and by so need to have a lower limit for the ngrams we kept
# for that languages
IDEOGRAM_LANGS = frozenset(['wuu','yue','cmn'])
IDEOGRAM_NGRAM_FREQ_LIMIT = 0.000005
NGRAM_FREQ_LIMIT = 0.00001
# number of 1-gram a user must have submitted in one language to
# be considered as possibly contributing in that languages
# NOTE: this number is currently purely arbitrary
USR_LANG_LIMIT = 400
# we will generate the ngram from 2-gram to X-grams
UP_TO_N_GRAM = 5
# some names of the table in the database
TABLE_NGRAM = "grams"
TABLE_STAT = "langstat"
TABLE_USR_STAT = "users_langs"
# database file name
DB = DB_DIR + 'ngrams.db'
INSERT_NGRAM = "INSERT INTO %s VALUES (?,?,?,?);"
INSERT_USR_STAT = "INSERT INTO %s VALUES (?,?,?);"


# create the database and all the required tables 
def generate_db():

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row;
    c = conn.cursor()

    for size in range(2,UP_TO_N_GRAM+1):

        table = TABLE_NGRAM + str(size)
        c.execute(
            """
            CREATE TABLE %s (
             'gram' text not null,
             'lang'text not null,
             'hit'  int not null,
             'percent' float not null default 0
            );
            """ % (table)
        );

    conn.commit()

    c.execute(
        """
        CREATE TABLE %s (
            'user' text not null,
            'lang' text not null ,
            'total' int not null default 0
        );
        """ % (TABLE_USR_STAT)
    )
    conn.commit()
    c.close()




def generate_n_grams():

    #tableStat = TABLE_STAT + str(size)
    conn = sqlite3.connect(DB)
    conn.isolation_level="EXCLUSIVE"
    conn.row_factory = sqlite3.Row;
    c = conn.cursor()
    # some optimization to make it faster
    c.execute('PRAGMA page_size=627680;')
    c.execute('pragma default_cache_size=320000;')
    c.execute('PRAGMA synchronous=OFF;')
    c.execute('PRAGMA count_changes=OFF;')
    c.execute('PRAGMA temp_store=MEMORY;')
    c.execute('PRAGMA journal_mode=MEMORY;')

    hyperLangNgram = []
    hyperLangNbrNgram = []

    for size in range(2,UP_TO_N_GRAM+1):
        hyperLangNbrNgram.append( 
            defaultdict(lambda: 0)
        )
        # lang => ngram => (hit,percent)
        hyperLangNgram.append(
            defaultdict(
                lambda: defaultdict(lambda: [0,0])
            )
        )

    userLangNbrNgram = defaultdict(lambda: 0)
    input = codecs.open(
        DB_DIR + SENTENCES_DETAILED,
        'r',
        encoding='utf-8'
    )
    for line in input:
        cols = line[:-1].split("\t")
        lang = cols[1]
        text = cols[2]
        user = cols[3]

        # we ignore the sentence with an unset language
        if lang == '\N':
            continue

        userLangNbrNgram[(user,lang)] += len(text)
        for size in range(2,UP_TO_N_GRAM+1):
            j = size - 2
            nbrNgramLine = len(text) - size
            hyperLangNbrNgram[j][lang] += nbrNgramLine
            currentLangNgram = hyperLangNgram[j][lang]
            for i in range(nbrNgramLine+1):
                ngram = text[i:i+size]
                currentLangNgram[ngram][0] += 1


    for i in range(0,UP_TO_N_GRAM-1):

        size = i + 2
        table = TABLE_NGRAM + str(size)
        
        langNgram = hyperLangNgram[i]
        langNbrNgram = hyperLangNbrNgram[i]
        for lang, currentLangNgram in langNgram.items():
            for ngram,tuple in currentLangNgram.items():
                hit = tuple[0]
                freq = float(hit) / langNbrNgram[lang]

                if lang in IDEOGRAM_LANGS:
                    if freq > IDEOGRAM_NGRAM_FREQ_LIMIT:
                        c.execute(
                            INSERT_NGRAM % (table),
                            (ngram,lang,hit,freq)
                        )
                else:
                    if freq > NGRAM_FREQ_LIMIT:

                        c.execute(
                            INSERT_NGRAM % (table),
                            (ngram,lang,hit,freq)
                            )
    for (user,lang),hit in userLangNbrNgram.items():
        if hit > USR_LANG_LIMIT:
            c.execute(
                INSERT_USR_STAT % (TABLE_USR_STAT),
                (user,lang,hit)
            )
    conn.commit()
    c.close()

# create indexes on the database to make request faster
def create_indexes_db():
    conn = sqlite3.connect(DB)
    conn.isolation_level="EXCLUSIVE"
    conn.row_factory = sqlite3.Row;
    c = conn.cursor()
    c.execute('PRAGMA page_size=627680;')
    c.execute('pragma default_cache_size=320000;')
    c.execute('PRAGMA synchronous=OFF;')
    c.execute('PRAGMA count_changes=OFF;')
    c.execute('PRAGMA temp_store=MEMORY;')
    c.execute('PRAGMA journal_mode=MEMORY;')


    for i in range(2,UP_TO_N_GRAM+1):
        c.execute(
            """
            CREATE INDEX
                gram_grams%d_idx
            ON grams%d(gram);
            """ % (i,i)
        )

    c.execute(
        """
        CREATE UNIQUE INDEX
            lang_user_users_langs_idx
        ON
            %s(lang,user);
        """ %(TABLE_USR_STAT)
    )
    c.execute(
        """
        CREATE INDEX
           user_%s_idx
        ON %s(user);
        """ % (TABLE_USR_STAT,TABLE_USR_STAT)
    )



    conn.commit()
    c.close()


# we first delete the old database
os.remove(DB)
# we download the file we will use
urllib.request.urlretrieve(
    URL_DL_FILES + SENTENCES_DETAILED,
    DB_DIR + SENTENCES_DETAILED
)

print("Download Finish")

generate_db()
generate_n_grams()

create_indexes_db()

#!/usr/bin/env python3
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
import sys
from collections import defaultdict

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
INSERT_NGRAM = "INSERT INTO %s VALUES (?,?,?,?);"
INSERT_USR_STAT = "INSERT INTO %s VALUES (?,?,?);"


# create the database and all the required tables 
def generate_db(database):

    conn = sqlite3.connect(database)
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

def sentencesWithTag(tagsFile, tagName):
    tagged = {}
    with open(tagsFile) as fp:
        for line in fp:
            try:
                cols = line[:-1].split("\t")
                sentenceId  = cols[0]
                sentenceTag = cols[1]
                if sentenceTag == tagName:
                    tagged[sentenceId] = True
            except IndexError:
                pass

    return tagged

def print_status_line(size, lineNumber):
    print('\rGenerating ngrams of size {} (reading CSV file... {} lines)'.format(size, lineNumber), end='')
    sys.stdout.flush()

def generate_n_grams(database, sentences_detailed, tags):

    #tableStat = TABLE_STAT + str(size)
    conn = sqlite3.connect(database)
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

    input = codecs.open(
        sentences_detailed,
        'r',
        encoding='utf-8'
    )

    wrongFlags = {}
    if tags:
        wrongFlags = sentencesWithTag(tags, '@change flag')

    userLangNbrNgram = defaultdict(lambda: 0)
    for size in range(UP_TO_N_GRAM, 1, -1):
        hyperLangNgram = defaultdict(
            lambda: defaultdict(lambda: 0)
        )
        hyperLangNbrNgram = defaultdict(lambda: 0)

        lineNumber = 0
        input.seek(0)
        for line in input:
            if lineNumber % 10000 == 0:
                print_status_line(size, lineNumber)

            lineNumber += 1
            try:
                cols = line[:-1].split("\t")
                sentenceId = cols[0]
                lang = cols[1]
                text = cols[2]
                user = cols[3]
            except IndexError:
                print('Skipped erroneous line {}: {}'.format(lineNumber, line))
                continue

            # we ignore the sentence with an unset language
            if lang == '\\N' or lang == '':
                continue

            # we ignore the sentence with wrong flag
            if sentenceId in wrongFlags:
                continue

            userLangNbrNgram[(user,lang)] += len(text)
            nbrNgramLine = len(text) - size + 1
            if nbrNgramLine > 0:
                hyperLangNbrNgram[lang] += nbrNgramLine
                for i in range(nbrNgramLine):
                    ngram = text[i:i+size]
                    hyperLangNgram[lang][ngram] += 1
        print_status_line(size, lineNumber)
        print(' done'.format(lineNumber))


        print('Inserting ngrams of size {}...'.format(size))

        table = TABLE_NGRAM + str(size)
        
        for lang, currentLangNgram in hyperLangNgram.items():
            for ngram,hit in currentLangNgram.items():
                freq = float(hit) / hyperLangNbrNgram[lang]

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
            conn.commit()

    print('Inserting user stats...')
    for (user,lang),hit in userLangNbrNgram.items():
        if hit > USR_LANG_LIMIT:
            c.execute(
                INSERT_USR_STAT % (TABLE_USR_STAT),
                (user,lang,hit)
            )
    conn.commit()
    c.close()

# create indexes on the database to make request faster
def create_indexes_db(database):
    conn = sqlite3.connect(database)
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

if len(sys.argv) < 3:
    print("Usage: {} <sentences_detailed.csv> <ngrams.db> [tags.csv]".format(sys.argv[0]))
    sys.exit(1)

sentences_detailed = sys.argv[1]
database = sys.argv[2]
try:
    tags = sys.argv[3]
except IndexError:
    tags = None

# we first delete the old database
if (os.path.isfile(database)):
    os.remove(database)

print("Start generating database...")
generate_db(database)

print("generating n-grams...")
generate_n_grams(database, sentences_detailed, tags)

print("creating indexes...")
create_indexes_db(database)

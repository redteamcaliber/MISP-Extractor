#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# MISP Data Manager
# Stores the data in a local sqlite database and maintain the data,
#  while keepping track of settings and last run.
#
# Software is free software released under the "Modified BSD license"
#
# Copyright (c) 2016 	Pieter-Jan Moreels - pieterjan.moreels@gmail.com

# Default Imports
import calendar
import datetime
import math
import os
import re
import sqlite3
import subprocess
import sys
import time

_runPath = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(_runPath, ".."))

import lib.Toolkit as TK
from lib.MispExtractor import MispExtractor

class MispDataManager():
  # Constructor for creating a new DB
  def __init__(self, dbpath, dataType=None, dataLife=None, key=None,
               url=None, analysis=None, threat=None):
    self.db     = DatabaseManager(dbpath)
    self.MispEx = MispExtractor(key=key, url=url)
    if dataType and dataLife and not os.path.isfile(dbpath):
      # This is a new DB, so create it
      self.db.writeSettings(0, 0, dataType, dataLife, analysis, threat)

  def fetchAndStoreData(self):
    settings = self.db.readSettings()
    now      = calendar.timegm(time.gmtime())
    since    = "%sm"%int(math.ceil((now - settings["lastrun"])/60))
    lifespan = TK.lifeSpanToMinutes(settings["datalife"])
    since    = since if int(since[:-1])<int(lifespan[:-1]) else lifespan
    data     = self.MispEx.getMISPData(since)
    matches  = self.MispEx.extractData(data, settings["datatype"],
                                             settings["analysis_level"],
                                             settings["threat_level"])
    self.db.storeData(matches)
    s = self.db.readSettings()
    
    self.db.writeSettings(s["lastrun"], now, s["datatype"], 
                          s["datalife"], s["analysis_level"],
                          s["threat_level"])
    self.cleanOldRecords()

  def cleanOldRecords(self):
    settings = self.db.readSettings()
    now      = calendar.timegm(time.gmtime())
    lifespan = TK.lifeSpanToMinutes(settings["datalife"])
    oldest   = now - (int(lifespan[:-1]) * 60)
    self.db.removeData("age <  %s"%oldest)

  def execCommandsOnData(self, dataset="all"):
    def parse(command, entry=None):
      # requirements for the regex
      def esc(i):  return str(i)
      def dformat(i): return format(i, "02")
      
      def rsub(text, replacement, command):
        I = re.IGNORECASE
        return re.compile(text, I).sub(esc(replacement), command)

      now = datetime.datetime.now()

      if entry:
        command=rsub('%hit%',    entry[0],                     command)
        command=rsub('%type%',   entry[1],                     command)
      command=rsub(  '%day%',    dformat(now.day),             command)
      command=rsub(  '%month%',  dformat(now.month),           command)
      command=rsub(  '%year%',   now.year,                     command)
      command=rsub(  '%hour%',   dformat(now.hour),            command)
      command=rsub(  '%minute%', dformat(now.minute),          command)
      command=rsub(  '%second%', dformat(now.second),          command)
      command=rsub(  '%path%',   os.path.join(_runPath, ".."), command)
      
      return command

    if   dataset == "new": data = self.db.fetchNewData()
    elif dataset == "old": data = self.db.fetchOldData()
    elif dataset == "all": data = self.db.fetchData()
    else: return
    commands = self.db.getCommands(dataset)
    # Command executed before the list
    if "initial" in commands.keys():
      subprocess.Popen(parse(commands["initial"]), shell=True)
    # Command on entry basis
    for entry in data:
      if entry[1] in commands.keys():
        subprocess.Popen(parse(commands[entry[1]], entry), shell=True)
    # Command executed after the list
    if "final" in commands.keys():
      subprocess.Popen(parse(commands["final"]), shell=True)

class DatabaseManager():
  def _dbWrapped(funct):
    def wrapper(self, *args, **kwargs):
      db = self.ensureDB()
      result = funct(self, db, *args, **kwargs)
      db.close()
      return result
    return wrapper

  def __init__(self, path):
    self.path = path
  
  def ensureDB(self):
    db=sqlite3.connect(self.path)
    db.execute('''CREATE TABLE IF NOT EXISTS MispData
                 (Value  TEXT     NOT NULL,
                  Type   TEXT     NOT NULL,
                  Age    INTEGER  NOT NULL,
                  PRIMARY KEY (Value, Type));''')
    db.execute('''CREATE TABLE IF NOT EXISTS Commands
                  (Type     TEXT  NOT NULL,
                   Command  TEXT  NOT NULL,
                   Dataset  TEXT  NOT NULL);''')
    db.execute('''CREATE TABLE IF NOT EXISTS Settings
                  (PreviousRun     INTEGER  NOT NULL,
                   LastRun         INTEGER  NOT NULL,
                   DataType        TEXT     NOT NULL,
                   DataLife        TEXT     NOT NULL,
                   Analysis_Level  INTEGER  DEFAULT 0,
                   Threat_Level    INTEGER  DEFAULT 4);''')
    return db

  # Settings
  @_dbWrapped
  def writeSettings(self, db, pr, lr, dt, dl, al, tl):
    if len(list(db.execute("SELECT * FROM Settings LIMIT 1"))) == 0:
      db.execute("""INSERT INTO Settings(PreviousRun, LastRun, DataType,
                                         DataLife, Analysis_Level,
                                         Threat_Level)
                    VALUES(?, ?, ?, ?, ?, ?)""",
                 (pr, lr, dt, dl, al, tl))
    else:
      db.execute("""UPDATE Settings
                    SET PreviousRun = ?, LastRun = ?, DataType = ?,
                        DataLife = ?, Analysis_Level = ?,
                        Threat_Level = ?""", (pr, lr, dt, dl, al, tl))
    db.commit()

  @_dbWrapped
  def readSettings(self, db):
    cur=db.cursor()
    data=list(cur.execute("SELECT * FROM Settings LIMIT 1"))
    names = list(map(lambda x: x[0], cur.description))
    if len(data) is 0: raise Exception("Corrupt Database")
    else:              data = data[0]
    # Make into dict
    settings={}
    for i in range(0,len(names)):
      settings[names[i].lower()]=data[i]
    return settings

  # Commands
  @_dbWrapped
  def addCommand(self, db, datatype, command, dataset):
    dataset  = dataset.lower()
    datatype = datatype.lower()
    if not dataset in ["all", "new", "old"]:
      raise Exception("Invalid dataset")
    db.execute("""INSERT INTO Commands(Type, Command, Dataset)
                  VALUES(?, ?, ?)""", (datatype, command, dataset))
    db.commit()

  @_dbWrapped
  def getCommands(self, db, dataset = "all"):
    if not dataset in ["all", "new", "old"]:
      raise Exception("Invalid dataset")
    where = " WHERE Dataset = '%s'"%dataset
    data=list(db.execute("SELECT Type, Command FROM Commands"+where))
    commands={x[0]: x[1] for x in data}
    return commands

  @_dbWrapped
  def dropCommands(self, db):
    db.execute("DELETE FROM Commands")
    db.commit()

  # Data
  @_dbWrapped
  def storeData(self, db, data):
    now   = calendar.timegm(time.gmtime())
    clean = [(line[2], line[1].lower(), now) for line in data]
    db.executemany("""INSERT OR IGNORE INTO MispData(Value, Type, Age)
                                            VALUES (?, ?, ?)""", clean)
    db.commit()

  @_dbWrapped
  def fetchData(self, db):
    data=list(db.execute("SELECT * FROM MispData"))
    return data

  @_dbWrapped
  def fetchNewData(self, db):
    data=list(db.execute("""SELECT * FROM MispData WHERE Age >= (
                              SELECT PreviousRun FROM Settings)"""))
    return data

  @_dbWrapped
  def fetchOldData(self, db):
    data=list(db.execute("""SELECT * FROM MispData WHERE Age < (
                              SELECT PreviousRun FROM Settings)"""))
    return data

  @_dbWrapped
  def removeData(self, db, where):
    db.execute("DELETE FROM MispData WHERE %s"%where)
    db.commit()

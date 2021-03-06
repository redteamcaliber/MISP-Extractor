#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Script to extract datasets from MISP via the API and return them in
#  CSV format.
#
# Software is free software released under the "Modified BSD license"
#
# Copyright (c) 2016 	Pieter-Jan Moreels - pieterjan.moreels@gmail.com

# Default Imports
import json
import os
import sys

_runPath = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(_runPath, ".."))

import lib.Toolkit as TK
from lib.MispExtractor import MispExtractor

def _output(data):
  if args.o:
    with open(args.o, "w") as w:
      w.write(data)
  else:
    print(data)

if __name__ == '__main__':
  import argparse
  argParser = argparse.ArgumentParser(description='Extract information from the MISP API')
  argParser.add_argument('-s', metavar="Since",     type=str,            help='Max age of the data (ex. 5m, 3h, 7d) "all" will return all')
  argParser.add_argument('-d', metavar="Data type", type=str,            help='Data to look for (domains|hashes|filenames|snort|yara)')
  argParser.add_argument('-t',                      action="store_true", help='Get DataTypes (Debug option')
  argParser.add_argument('-e',                      action="store_true", help='Get Examples (Debug option')
  argParser.add_argument('-o', metavar="file",      type=str,            help='Output file (default stdout)')
  argParser.add_argument('-u', metavar="MISP URL",  type=str,            help='The URL to the MISP API')
  argParser.add_argument('-k', metavar="MISP Key",  type=str,            help='Your API key for the MISP API')
  argParser.add_argument('-H',                      action="store_true", help='Include headers to the output')
  argParser.add_argument('-S', metavar="separator", type=str,            help='Separator for the output (default ",")')
  argParser.add_argument('-A', metavar="integer",   type=int,            help='Analysis level (0: Initial, 1: Ongoing, 2: Completed)')
  argParser.add_argument('-T', metavar="integer",   type=int,            help='Threat level (4: Undefined, 3: Low, 2: Medium, 1: High)')
  args = argParser.parse_args()

  if not (args.t or args.e or args.d):
    sys.exit("Please choose an option")

  MispEx = MispExtractor(key=args.k, url=args.u)

  data = MispEx.getMISPData(args.s)
  
  if args.t:
    print(json.dumps(MispEx.getTypes(data), indent=2, sort_keys=True))
  elif args.e:
    MispEx.getExample(data)
  elif args.d:
    search = args.d.lower()
    if search not in MispEx.searches.keys():
      sys.exit("Please use a valid search term")
    matches = MispEx.extractData(data, search, threat_level=args.T,
                                               analysis_level=args.A)
    output  = TK.generateCSV(matches)
    _output(output)

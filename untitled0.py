# -*- coding: utf-8 -*-
"""
Created on Mon Mar 18 14:39:39 2024

@author: UWTUCANMag
"""

import pandas as pd

df = pd.read_csv('C:/Users/mlavvaf/Desktop/Maedeh/MCCDAQ/MCCDAQ/data_2024-03-28_13-34-53.csv')

print(df.head())

# Extract column labels for all channels
channels = ['Channel {}'.format(i) for i in range(3)]

# Plot all channels
df.plot(x='Time', y=channels).grid()

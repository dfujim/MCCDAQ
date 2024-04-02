# -*- coding: utf-8 -*-
"""
Created on Mon Mar 18 14:39:39 2024

@author: UWTUCANMag
"""

import pandas as pd

df = pd.read_csv('C:/Users/mlavvaf/Desktop/Maedeh/MCCDAQ/data_files/data_2024-04-02_15-47-22.csv')
# df = df[5:]

print(df.head())

# Extract column labels for all channels
channels = ['Channel {}'.format(i) for i in range(1)]

# Plot all channels
df.plot(x='Time', y=channels).grid()

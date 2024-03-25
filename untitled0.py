# -*- coding: utf-8 -*-
"""
Created on Mon Mar 18 14:39:39 2024

@author: UWTUCANMag
"""

import pandas as pd

df = pd.read_csv('C:/Users/UWTUCANMag/Desktop/MSR/MCCDAQ/data_2024-03-24_21-43-50.csv')

print(df.head())

df.plot(x='Time', y='Channel 0')
# df['Channel 0'].plot()
# df['Channel 2'].plot()
# df['Channel 3'].plot()


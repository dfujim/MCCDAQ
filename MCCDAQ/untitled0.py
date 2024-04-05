# -*- coding: utf-8 -*-
"""
Created on Mon Mar 18 14:39:39 2024

@author: UWTUCANMag
"""

import pandas as pd
import matplotlib.pyplot as plt

# Read the CSV file into a DataFrame, skipping any rows that start with '#'
df = pd.read_csv('C:/Users/mlavvaf/Desktop/Maedeh/MCCDAQ/data_files/data_2024-04-05_15-52-19.csv',
                 comment='#')

# Plot every column against the "Time" column
for column in df.columns:
    if column != 'Time (s)':  # Skip plotting against the "Time" column itself
        plt.plot(df['Time (s)'], df[column], label=column)

# Add labels and legend
plt.xlabel('Time (s)')
plt.ylabel('Value')
plt.legend()
plt.grid()

# Show the plot
plt.show()



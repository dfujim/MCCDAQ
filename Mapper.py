# -*- coding: utf-8 -*-
"""
Created on Fri Apr 19 15:54:32 2024

@author: mlavvaf
"""

import sys
import os
from statistics import mean
from MCCDAQ import *


class Map(MCCDAQ):
    def __init__(self, **setting):

        rate = setting.pop('rate', 10000)
        self.begin = setting['begin']
        self.end = setting['end']
        self.pos_calibration_result = []  # Initialize result attributes
        self.b_calibration_result = {}
        super().__init__(rate=rate, dur=1, **setting)

    def setup(self):
        """Call setup from MCCDAQ.

        Returns
        -------
        Func
            Setup function.

        """
        return super().setup(channels)

    def to_df(self):
        """Convert data to DataFrame.

        Returns
        -------
        None.

        """
        super()._to_df()  # Call the parent method to create the DataFrame

        # Add pos_calibration and b_calibration columns
        self.df['Pos (cm)'] = self.pos_calibration_result

        # Construct column names for magnetic field channels
        channel_counter = 1
        for i in range(1, self.num_chan):  # Adjust range based on num_chan
            # Construct column name dynamically
            channel_name = f'{channels[i]} (T)'
            self.df[channel_name] = self.b_calibration_result.get(
                channel_counter, [])  # Use .get() to handle missing channels

            channel_counter += 1

    def pos_calibration(self, channels, calibration):
        """Convert values of the potentiometer from voltage to cm.

        Parameters
        ----------
        channels : dict
            Contains channels names and values.
        calibration : Bool
            Can be used to calibrate by user or the device calibration value.

        Returns
        -------
        None.

        """
        v_0 = mean(self.channel_data[0][:50])   # 0 is CH0H: potentiometer
        v_1 = mean(self.channel_data[0][-50:])

        if calibration == False:
            slope = 1 / 35
        else:
            slope = (v_1 - v_0) / (self.end - self.begin)

        intercept = v_0

        # Extract data values excluding the header
        data_values = self.channel_data[0]

        # Initialize the result list with the header
        result = []

        for v in data_values:
            if isinstance(v, str):
                # Preserve non-numeric values
                result.append(v)
            else:
                try:
                    float_v = float(v)
                    converted_value = (float_v - intercept) / slope
                    result.append(converted_value)  # Append converted value
                except ValueError:
                    # If conversion fails, preserve the original value
                    result.append(v)
        self.pos_calibration_result = result  # Assign result to instance attribute

    def b_calibration(self, channels, **setting):
        """Calibrate fluxgate values.

        Parameters
        ----------
        channels : dict
            Contains channels names and values.
        **setting : dict
            Board number and number of channels must be defined in the
            setting dictionary. Any comments can be added.

        Returns
        -------
        None.

        """
        # Initialize dictionary to store data values and results for each channel
        data_values = {}
        result = {}

        # Extract data values excluding the header for channels 2 to 7
        for i in range(1, self.num_chan):
            data_values[i] = self.channel_data[i]

            # Initialize the result list with the header
            result[i] = []

            for v in data_values[i]:
                if isinstance(v, str):
                    # Preserve non-numeric values
                    result[i].append(v)
                else:
                    try:
                        float_v = float(v)
                        converted_value = (float_v * setting['fluxgate_range']) / \
                                          (setting['SCU1_gain'] * 10)
                        # Append converted value
                        result[i].append(converted_value)
                    except ValueError:
                        # If conversion fails, preserve the original value
                        result[i].append(v)
            # Assign result to instance attribute
            self.b_calibration_result[i] = result[i]


if __name__ == "__main__":

    setting = {"board_num":         0,
               "num_chan":          4,
               "hole_number":       17,
               "SCU1_gain":         50,
               "fluxgate_range":    100,
               "wall":              "east",
               "begin":             int(input("\nEnter start point in cm: ")),
               "end":               int(input("\nEnter stop point in cm: ")),
               "Comment1":          "Battery is 1.5V",
               "Comment2":          "FG V_pp is 4V changed to 2V"}

    channels = {0: "Potmet",          # CH0H
                1: "Ground",          # CH0L
                2: "Bx",              # CH1H
                3: "Gx",              # CH1L
                4: "By",              # CH2H
                5: "Gy",              # CH2L
                6: "Bz",              # CH3H
                7: "Gz",              # CH3L
                }

    map_instance = Map(**setting)  # Create an instance of Map

    script_directory = os.path.dirname(os.path.abspath(sys.argv[0]))

    directory_path = os.path.join(script_directory, "..", "data_files")

    map_instance.setup()                      # CH1H

    try:
        while True:
            command = input(
                "\nEnter command (start(s)/ pause(p)/ exit(e)): ")

            if command.lower() == "s":
                map_instance.start(directory_path)
            elif command.lower() == "p":
                map_instance.stop()
            elif command.lower() == "e":
                break
            else:
                print("Invalid command. Please enter start(s)/ pause(p)/ exit(e).")

        map_instance.pos_calibration(channels, calibration=False)
        map_instance.b_calibration(channels, **setting)

        map_instance.to_df()  # Explicitly call to_df() before saving to CSV
        map_instance.to_csv(**setting)

    except KeyboardInterrupt:
        print("\nReceived KeyboardInterrupt.\
              Stopping acquisition and exiting...")
        map_instance.stop()


"""
Scans a range of A/D Input Channels from MCCDAQ E-1608 and stores the sample data in a file.

Created on Sun Mar 24 18:51:06 2024

@author: Maedeh Lavvaf
"""

from __future__ import absolute_import, division, print_function, annotations
# from builtins import *
from ctypes import c_double, cast, POINTER, addressof, sizeof
from time import sleep
from mcculw import ul
from mcculw.enums import (ScanOptions, FunctionType, Status, AnalogInputMode,
                          InterfaceType, ULRange)
import csv
import os
import sys
import datetime
import logging
import threading
import numpy as np
import pandas as pd


class E1608(object):

    def __init__(self, rate=10000, dur=1, **setting):
        """Initialize parameters.

        Parameters
        ----------
        rate : int, optional
            Sample rate in Samples/second. The default is 10000.

        dur : int, optional
            Total time of taking every chunk of data. The default is 1.

        **setting : dict
            Board number and number of channels must be defined in the
            setting dictionary. Any comments can be added.

        Returns
        -------
        None.

        """
        # ******* device info *******
        self.setting = setting
        self.board_num = setting["board_num"]
        self.dev_id_list = []
        self.low_chan = 0
        self.high_chan = None

        # total number of a ai channels
        self.num_chan = setting["num_chan"]

        # ******* sampling requirements *******

        # The number of buffers to write. After this number of UL buffers are
        # written to file, the example will be stopped.
        self.num_buffers_to_write = 1

        # sample rate in samples/second
        self.rate = rate

        # the name of the desire device that can be found by running the
        # current code. (The name of all connected devices will be printed.)
        self.find_device = "E-1608-394C95"

        # sample period in second
        self.dur = dur
        self.file_name = None
        self.channels = setting.get("channels", {})  # User-defined channels
        self.channel_data = [[] for _ in range(setting["num_chan"])]

        self.logging_initialized = False
        self.thread = None
        self.stop_event = threading.Event()

    def _device_detection(self, dev_id_list=None):
        """Add the first available device to the UL.
        If a types_list is specified,
        the first available device in the types list will be add to the UL.

        Parameters
        ----------
        board_num :     int
                        The board number to assign to the board when
                        configuring the device.

        dev_id_list :   list[int], optional
                        A list of product IDs used to filter the results.
                        Default is None.
                        See UL documentation for device IDs.
        """
        ul.ignore_instacal()
        devices = ul.get_daq_device_inventory(InterfaceType.ANY)
        if not devices:
            raise IOError('Error: No DAQ devices found')

        print('Found', len(devices), 'DAQ device(s):')
        for device in devices:
            print('  ', device.product_name, ' (', device.unique_id, ') - ',
                  'Device ID = ', device.product_id, sep='')

        device = devices[0]
        if dev_id_list:
            device = next((device for device in devices
                           if device.product_id in dev_id_list), None)
            if not device:
                err_str = 'Error: No DAQ device found in device ID list: '
                err_str += ','.join(str(dev_id) for dev_id in dev_id_list)
                raise RuntimeError(err_str)

        # Add the first DAQ device to the UL with the specified board number
        ul.create_daq_device(self.board_num, device)

    def setup(self, channels=None):
        """Connect to necessary equipment and setup any necessary parameters.

        Parameters
        ----------
        channels : dict, optional
            The name of each channel that will appear in the header of the
            csv file. The default is None.

        Raises
        ------
        MemoryError
            If the buffer is not successfully allocated.

        Returns
        -------
        None.

        """
        if channels is not None:
            self.channels = channels

        # set device to "Single Ended" mode. Other optin is "Differential"
        ul.a_input_mode(self.board_num, AnalogInputMode.SINGLE_ENDED)

        # The number of high channel on the board. (total number of using
        # channel -1 since it starts from 0)
        self.high_chan = self.num_chan - 1
        # self.high_chan = 1

        # buffer sized to hold one second of data.
        # Make larger if your data handling requires more.
        points_per_channel = max(self.rate * self.dur, 10)

        # Total points
        ul_buffer_count = points_per_channel * self.num_chan

        # Write the UL buffer to the file num_buffers_to_write times.
        # points_to_write = ul_buffer_count * self.num_buffers_to_write

        # When handling the buffer, we will read 1/10 of the buffer at a time
        write_chunk_size = int(ul_buffer_count / 10)

        # AI range set to +/- 10 volts which is its max.
        ai_range = ULRange.BIP10VOLTS

        # The SCALEDATA option, returns volts instead of A/D counts
        scan_options = (ScanOptions.BACKGROUND | ScanOptions.CONTINUOUS |
                        ScanOptions.SCALEDATA)

        memhandle = ul.scaled_win_buf_alloc(ul_buffer_count)

        # Check if the buffer was successfully allocated
        if not memhandle:
            raise MemoryError('Failed to allocate memory')

        self.scan_params = {
            'ul_buffer_count': ul_buffer_count,
            # 'points_to_write': points_to_write,
            'write_chunk_size': write_chunk_size,
            'ai_range': ai_range,
            'scan_options': scan_options,
            'memhandle': memhandle
        }

    def _initialize_logging(self):
        """Set up the logging configuration for the DataAcquisition class,
        defining the logging level, format, and output stream for log messages.

        Returns
        -------
        None.

        """
        if not self.logging_initialized:
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(levelname)s - %(message)s',
                stream=sys.stdout)
            self.logger = logging.getLogger('DataAcquisition')
            self.logging_initialized = True

    def start(self, directory):
        """Start data acquisition.

        Parameters
        ----------
        directory : str
            Directory of saving csv file.

        Returns
        -------
        None.

        """
        self.stop_event.clear()  # Reset stop event
        self.generate_file_name(directory)
        self._device_detection(self.board_num)
        self.setup()
        self._initialize_logging()
        self.logger.info("\n\n Starting data acquisition...\n")
        self.thread = threading.Thread(target=self._acquire_data)
        self.thread.start()

    def stop(self):
        """Stop data acquisition.

        Returns
        -------
        None.

        """
        self.stop_event.set()
        self.thread.join()
        self.logger.info("\n\n Data acquisition stopped.")

    def _acquire_data(self):
        """Start the scan and acquire data.

        Returns
        -------
        None.

        """
        use_device_detection = True

        ul.a_in_scan(self.board_num, self.low_chan, self.high_chan,
                     self.scan_params['ul_buffer_count'],
                     self.rate, self.scan_params['ai_range'],
                     self.scan_params['memhandle'],
                     self.scan_params['scan_options'])

        status = Status.IDLE
        # Wait for the scan to start fully
        while status == Status.IDLE:
            # Get the status from the device
            status, _, _ = ul.get_status(
                self.board_num, FunctionType.AIFUNCTION)

        # Start the write loop
        prev_count = 0
        prev_index = 0
        write_ch_num = self.low_chan
        write_chunk_array = (c_double * self.scan_params['write_chunk_size'])()

        while status != Status.IDLE:
            # Check if the stop event has been set
            if self.stop_event.is_set():
                break  # Exit the loop if stop event is set

            # Get the latest counts
            status, curr_count, _ = ul.get_status(
                self.board_num, FunctionType.AIFUNCTION)

            new_data_count = curr_count - prev_count

            # Check for a buffer overrun before copying the data
            if new_data_count > self.scan_params['ul_buffer_count']:
                # Print an error and stop writing
                ul.stop_background(self.board_num, FunctionType.AIFUNCTION)
                print('A buffer overrun occurred')
                break

            # Check if a chunk is available
            if new_data_count > self.scan_params['write_chunk_size']:
                wrote_chunk = True
                # Copy the current data to a new array

                # Check if the data wraps around the end of the UL buffer
                if prev_index + self.scan_params['write_chunk_size'] > \
                        self.scan_params['ul_buffer_count'] - 1:

                    first_chunk_size = self.scan_params['ul_buffer_count'] - \
                        prev_index

                    second_chunk_size = (
                        self.scan_params['write_chunk_size'] -
                        first_chunk_size)

                    # Copy the first chunk of data to the write_chunk_array
                    ul.scaled_win_buf_to_array(self.scan_params['memhandle'],
                                               write_chunk_array, prev_index,
                                               first_chunk_size)

                    # Create a pointer to the location in write_chunk_array where we want to copy the remaining data
                    second_chunk_pointer = cast(addressof(write_chunk_array)
                                                + first_chunk_size
                                                * sizeof(c_double),
                                                POINTER(c_double))

                    # Copy the second chunk of data to the write_chunk_array
                    ul.scaled_win_buf_to_array(self.scan_params['memhandle'],
                                               second_chunk_pointer, 0,
                                               second_chunk_size)
                else:
                    # Copy the data to the write_chunk_array
                    ul.scaled_win_buf_to_array(
                        self.scan_params['memhandle'], write_chunk_array,
                        prev_index, self.scan_params['write_chunk_size'])

                # Check for a buffer overrun just after copying the data from the UL buffer
                status, curr_count, _ = ul.get_status(
                    self.board_num, FunctionType.AIFUNCTION)

                if curr_count - prev_count > \
                        self.scan_params['ul_buffer_count']:
                    # Print an error and stop writing
                    ul.stop_background(self.board_num, FunctionType.AIFUNCTION)
                    print('A buffer overrun occurred')
                    break

                for i in range(self.scan_params['write_chunk_size']):
                    # Append data to corresponding channel array
                    self.channel_data[write_ch_num].append(
                        write_chunk_array[i])
                    write_ch_num += 1
                    if write_ch_num == self.high_chan + 1:
                        write_ch_num = self.low_chan
            else:
                wrote_chunk = False

            if wrote_chunk:
                # Increment prev_count by the chunk size
                prev_count += self.scan_params['write_chunk_size']

                # Increment prev_index by the chunk size
                prev_index += self.scan_params['write_chunk_size']

                # Wrap prev_index to the size of the UL buffer
                prev_index %= self.scan_params['ul_buffer_count']

                # if prev_count >= self.scan_params['points_to_write']:
                #     break
                print('.', end='')
            else:
                # Wait a short amount of time for more data to be acquired.
                sleep(0.1)

        ul.stop_background(self.board_num, FunctionType.AIFUNCTION)

        # Free the buffer in a finally block to prevent a memory leak.
        if self.scan_params['memhandle']:
            ul.win_buf_free(self.scan_params['memhandle'])

    def generate_file_name(self, directory):
        """Automatically generates file name based on the date of creation.

        Parameters
        ----------
        directory : str
            Directory path where the file should be saved.

        Returns
        -------
        None.

        """
        current_datetime = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        # Create the directory if it doesn't exist
        os.makedirs(directory, exist_ok=True)

        file_path = os.path.join(directory, f"data_{current_datetime}.csv")
        self.file_name = file_path

    def _to_df(self):
        # Create a time array
        num_samples = len(self.channel_data[0])  # Assuming all channels have the same length
        sample_period = 1 / self.rate
        time_array = np.arange(0, num_samples)*sample_period

        # Create channel labels
        channel_labels = [self.channels.get(
            i, f"CH{i}") for i in range(self.num_chan)]

        # Create dict for DataFrame
        data_dict = {"Time (s)": time_array}
        for i, label in enumerate(channel_labels):
            data_dict[label] = self.channel_data[i]

        # get shortest list and trim to length
        len_shortest = min([len(ch) for ch in data_dict.values])
        for key, val in data_dict.items():
            data_dict[key] = val[:len_shortest]

        # make dataframe
        self.df = pd.DataFrame(data_dict)

    def to_csv(self, filename=None, downsample=1, **setting):
        """Save the whole data in a csv file.

        Parameters
        ----------
        filename : str, optional
            The file name to save the data to. If not provided, it will use
            the automatically generated file name.
        setting : dict
            Additional settings to include in the header.

        Returns
        -------
        None.
        """
        if filename is None:
            filename = self.file_name

        header = ['# Physical settings:']
        string_len = max([len(s) for s in setting.keys()]) + 2
        header.extend(
            [f'#    {key:{string_len}}: {value}' for key, value in setting.items()])
        header.append('#\n')

        self.to_df()  # Convert channel data to DataFrame

        # downsample
        self.df = self.df.loc[::downsample]

        if hasattr(self, 'df') and not self.df.empty:
            with open(filename, 'w', newline='') as csvfile:
                csvfile.write('\n'.join(header))
                self.df.to_csv(csvfile, index=False)  # Save DataFrame to CSV
            print(f"Data saved to {filename} successfully.")
        else:
            print("No data available to save.")




if __name__ == "__main__":

    setting = {"board_num":      0,
                "num_chan":      2,
                "Comment1":      "Battery is 1.5V",
                "Comment2":      "FG V_pp is 4V changed to 2V"}

    script_directory = os.path.dirname(os.path.abspath(sys.argv[0]))

    directory_path = os.path.join(script_directory, "..", "data_files")

    data_acquisition = E1608(**setting)

    data_acquisition.setup(channels={0: "Potmet",  # CH0H
                                      1: "Ground",  # CH0L
                                      })            # CH1H

    try:
        while True:
            command = input("\nEnter command (start(s)/ pause(p)/ exit(e)): ")
            if command.lower() == "s":
                data_acquisition.start(directory_path)
            elif command.lower() == "p":
                data_acquisition.stop()
            elif command.lower() == "e":
                break
            else:
                print("Invalid command. Please enter 's' or 'p' or 'e'.")

        data_acquisition.to_csv(**setting)

    except KeyboardInterrupt:
        print("\nReceived KeyboardInterrupt.\
              Stopping acquisition and exiting...")
        data_acquisition.stop()

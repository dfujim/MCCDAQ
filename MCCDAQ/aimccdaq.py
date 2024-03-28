"""
Scans a range of A/D Input Channels from MCCDAQ E-1608 and stores the sample data in a file. 

Created on Sun Mar 24 18:51:06 2024

@author: Maedeh Lavvaf
"""

# from __future__ import absolute_import, division, print_function
# from builtins import *
from ctypes import c_double, cast, POINTER, addressof, sizeof, c_ushort, c_ulong
from time import sleep
from mcculw import ul
from mcculw.enums import (ScanOptions, FunctionType, Status, AnalogInputMode,
                          InterfaceType, ULRange)
from mcculw.device_info import DaqDeviceInfo
from mcculw.ul import ULError, a_input_mode
import time
import csv
import os
import datetime


class DataAcquisition:
    def __init__(self, board_num, rate, dur, num_chan):
        """Initialize parameters.

        Parameters
        ----------
        board_num : int
            Board number provided by InstaCal software.

        rate : int
            Sample rate in Samples/second.

        dur : int
            Total time of taking data.

        num_chan : int
            Number of AI channels taking data.

        Returns
        -------
        None.

        """
        # ******* device info *******

        self.board_num = board_num
        self.dev_id_list = []
        self.low_chan = 0
        self.high_chan = None

        # total number of a ai channels
        self.num_chan = num_chan

        # ******* sampling requirements *******

        # The number of buffers to write. After this number of UL buffers are
        # written to file, the example will be stopped.
        self.num_buffers_to_write = dur

        # sample rate in samples/second
        self.rate = rate

        # the name of the desire device that can be found by running the
        # current code. (The name of all connected devices will be printed.)
        self.find_device = "E-1608-394C95"

        # sample period in second
        self.dur = dur
        self.file_name = None
        self.channel_data = [[] for _ in range(num_chan)]

    def setup(self):
        """Connect to necessary equipment and setup any necessary parameters.

        Raises
        ------
        Exception
            If the buffer is not successfully allocated..

        Returns
        -------
        None.

        """
        # If use_device_detection is set to False, the board_num variable needs
        # to match the desired board number configured with Instacal software.
        if use_device_detection:

            # set board number to -1 to check error if device not found.
            self.board_num = -1

            # index of the boards in the dev_id_list array.
            self.board_index = 0

            ul.ignore_instacal()

            # Collecting all connected devices
            self.dev_id_list = ul.get_daq_device_inventory(InterfaceType.ANY)

            if len(self.dev_id_list) > 0:

                for device in self.dev_id_list:
                    print('Connected device', device, end='\n\n')

                print(
                    f"Found {self.find_device} \
                    board number = {self.board_index}", end='\n\n')
                print(f"Serial number: {device.unique_id}")
                print(f"Product type: {hex(device.product_id)}")

                self.board_num = self.board_index

                # Creating the device to take its info and set it up
                ul.create_daq_device(self.board_num, device)

                self.board_index = self.board_index + 1

                if self.board_num == -1:
                    print(f"Device {self.find_device} not found")
            else:
                print("No devices detected")

        # set device to "Single Ended" mode. Other optin is "Differential"
        ul.a_input_mode(self.board_num, AnalogInputMode.SINGLE_ENDED)

        # The number of high channel on the board. (total number of using
        # channel -1 since it starts from 0)
        self.high_chan = self.num_chan - 1

        # buffer sized to hold one second of data.
        # Make larger if your data handling requires more.
        points_per_channel = max(self.rate, 10)

        # Total points
        ul_buffer_count = points_per_channel * self.num_chan

        # Write the UL buffer to the file num_buffers_to_write times.
        points_to_write = ul_buffer_count * self.num_buffers_to_write

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
            raise Exception('Failed to allocate memory')

        self.scan_params = {
            'ul_buffer_count': ul_buffer_count,
            'points_to_write': points_to_write,
            'write_chunk_size': write_chunk_size,
            'ai_range': ai_range,
            'scan_options': scan_options,
            'memhandle': memhandle
        }

    def acquire_data(self):
        """Start the scan and acquire data."""
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

                    # Create a pointer to the location in write_chunk_array
                    # where we want to copy the remaining data
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

                # Check for a buffer overrun just after copying
                # the data from the UL buffer
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

                if prev_count >= self.scan_params['points_to_write']:
                    break
                print('.', end='')
            else:
                # Wait a short amount of time for more data to be acquired.
                sleep(0.1)

        ul.stop_background(self.board_num, FunctionType.AIFUNCTION)

        # Free the buffer in a finally block to prevent a memory leak.
        if self.scan_params['memhandle']:
            ul.win_buf_free(self.scan_params['memhandle'])

        if use_device_detection:
            ul.release_daq_device(self.board_num)

    def generate_file_name(self):
        """Automatically generates file name based on the date of creation.

        Returns
        -------
        None.

        """
        current_datetime = datetime.datetime.now().\
            strftime("%Y-%m-%d_%H-%M-%S")

        self.file_name = f"data_{current_datetime}.csv"

    def to_csv(self):
        """Save data in a csv file.

        Returns
        -------
        None.

        """
        if self.channel_data:
            time_values = [
                i / self.rate for i in range(len(self.channel_data[0]))]
            with open(self.file_name, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                header = ['Time'] + \
                    ['Channel {}'.format(i) for i in range(self.num_chan)]
                writer.writerow(header)
                for i, time_val in enumerate(time_values):
                    # Write data for each channel at corresponding time
                    row = [time_val] + [channel_data[i]
                                        for channel_data in self.channel_data]
                    writer.writerow(row)
            print(f"Data saved to {self.file_name} successfully.")
        else:
            print("No data available to save.")


if __name__ == "__main__":
    use_device_detection = True
    board_num = 0
    rate = 10000  # number of points per second per buffer
    dur = 1
    num_chan = 1
    data_acquisition = DataAcquisition(board_num, rate, dur, num_chan)
    data_acquisition.setup()
    data_acquisition.acquire_data()
    data_acquisition.generate_file_name()  # Generate dynamic file name
    data_acquisition.to_csv()

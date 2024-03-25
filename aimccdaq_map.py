from ctypes import c_double, cast, POINTER, addressof, sizeof
from time import sleep
from mcculw import ul
from mcculw.enums import (ScanOptions, FunctionType, Status, AnalogInputMode,
                          InterfaceType, ULRange)
import csv
import os
import datetime
import sys

class DataAcquisition:
    def __init__(self, board_num, find_device, rate, dur, save_dir):
        self.board_num = board_num
        self.rate = rate
        self.dur = dur
        self.file_name = None
        self.dev_id_list = []
        self.low_chan = 0
        self.high_chan = None
        self.num_buffers_to_write = 1
        self.data = []
        self.find_device = find_device
        self.num_chan = 1
        self.save_dir = save_dir

    def setup(self):

        if use_device_detection:
            self.board_num = -1
            self.board_index = 0
            ul.ignore_instacal()
            self.dev_id_list = ul.get_daq_device_inventory(InterfaceType.ANY)
            if len(self.dev_id_list) > 0:
                for device in self.dev_id_list:
                    if str(device).strip() == self.find_device:
                        print(
                            f"Found {find_device} board number = {self.board_index}")
                        print(f"Serial number: {device.unique_id}")
                        print(f"Product type: {hex(device.product_id)}")
                        self.board_num = self.board_index
                        ul.create_daq_device(self.board_num, device)
                    self.board_index = self.board_index + 1

                if self.board_num == -1:
                    print(f"Device {find_device} not found")
            else:
                print("No devices detected")

        ul.a_input_mode(self.board_num, AnalogInputMode.SINGLE_ENDED)

        self.high_chan = 0
        points_per_channel = max(self.rate * self.dur, 10)
        ul_buffer_count = points_per_channel * \
            (self.high_chan - self.low_chan + 1)
        points_to_write = ul_buffer_count * self.num_buffers_to_write
        write_chunk_size = int(ul_buffer_count / 10)
        ai_range = ULRange.BIP10VOLTS
        scan_options = (ScanOptions.BACKGROUND | ScanOptions.CONTINUOUS |
                        ScanOptions.SCALEDATA)
        memhandle = ul.scaled_win_buf_alloc(ul_buffer_count)
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
        
    def stop(self):
        ul.stop_background(self.board_num, FunctionType.AIFUNCTION)
        print("Data acquisition stopped.")

    def acquire_data_single_point(self):
        
        self.stop()
        
        ul.a_in_scan(self.board_num, self.low_chan, self.high_chan,
                     self.scan_params['ul_buffer_count'],
                     self.rate, self.scan_params['ai_range'],
                     self.scan_params['memhandle'],
                     self.scan_params['scan_options'])

        status = Status.IDLE
        while status == Status.IDLE:
            status, _, _ = ul.get_status(
                self.board_num, FunctionType.AIFUNCTION)

        prev_count = 0
        prev_index = 0
        write_ch_num = self.low_chan
        write_chunk_array = (c_double * self.scan_params['write_chunk_size'])()

        while status != Status.IDLE:
            status, curr_count, _ = ul.get_status(
                self.board_num, FunctionType.AIFUNCTION)

            new_data_count = curr_count - prev_count

            if new_data_count > self.scan_params['ul_buffer_count']:
                ul.stop_background(self.board_num, FunctionType.AIFUNCTION)
                print('A buffer overrun occurred')
                break

            if new_data_count > self.scan_params['write_chunk_size']:
                wrote_chunk = True

                if prev_index + self.scan_params['write_chunk_size'] > self.scan_params['ul_buffer_count'] - 1:
                    first_chunk_size = self.scan_params['ul_buffer_count'] - prev_index
                    second_chunk_size = (
                        self.scan_params['write_chunk_size'] - first_chunk_size)

                    ul.scaled_win_buf_to_array(self.scan_params['memhandle'],
                                               write_chunk_array, prev_index, 
                                               first_chunk_size)

                    second_chunk_pointer = cast(addressof(write_chunk_array)
                                                + first_chunk_size
                                                * sizeof(c_double),
                                                POINTER(c_double))

                    ul.scaled_win_buf_to_array(self.scan_params['memhandle'],
                                               second_chunk_pointer, 0, 
                                               second_chunk_size)
                else:
                    ul.scaled_win_buf_to_array(
                        self.scan_params['memhandle'], write_chunk_array,
                        prev_index, self.scan_params['write_chunk_size'])

                status, curr_count, _ = ul.get_status(
                    self.board_num, FunctionType.AIFUNCTION)

                if curr_count - prev_count > self.scan_params['ul_buffer_count']:
                    ul.stop_background(self.board_num, FunctionType.AIFUNCTION)
                    print('A buffer overrun occurred')
                    break

                for i in range(self.scan_params['write_chunk_size']):
                    self.data.append(write_chunk_array[i])
                    write_ch_num += 1
                    if write_ch_num == self.high_chan + 1:
                        write_ch_num = self.low_chan
            else:
                wrote_chunk = False

            if wrote_chunk:
                prev_count += self.scan_params['write_chunk_size']
                prev_index += self.scan_params['write_chunk_size']
                prev_index %= self.scan_params['ul_buffer_count']

                if prev_count >= self.scan_params['points_to_write']:
                    break
                print('.', end='')
            else:
                sleep(0.1)

        # ul.stop_background(self.board_num, FunctionType.AIFUNCTION)
        if self.scan_params['memhandle']:
            ul.win_buf_free(self.scan_params['memhandle'])
        if use_device_detection:
            ul.release_daq_device(self.board_num)

    def acquire_data_range(self, range_start, range_stop):
        while range_start <= range_stop:
            print(f"Acquiring data for position {range_start}")
            input("Press Enter to start acquisition...")
            self.data = []  # Reset data
            self.acquire_data_single_point()
            self.generate_file_name()
            self.to_csv()
            range_start += 1

    def generate_file_name(self):
        current_datetime = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.file_name = f"data_{current_datetime}.csv"

    def to_csv(self):
        if self.data:
            time_values = [i / self.rate for i in range(len(self.data))]
            file_path = os.path.join(self.save_dir, self.file_name)  # Construct full file path
            with open(file_path, 'a', newline='') as csvfile:  # Open file in provided directory
                writer = csv.writer(csvfile)
                header = ['Time'] + \
                    ['Channel {}'.format(i) for i in range(self.num_chan)]
                writer.writerow(header)  # Header for the columns
                for time_val, value in zip(time_values, self.data):
                    writer.writerow([time_val] + [value])
            print(f"Data appended to {file_path} successfully.")
        else:
            print("No data available to save.")



if __name__ == "__main__":
    use_device_detection = True
    find_device = "E-1608-394C95"
    board_num = 0
    rate = 1000  # number of points per second per buffer
    dur = 1
    save_dir = 'C:/Users/UWTUCANMag/Desktop/MSR/MCCDAQ/test/'
    data_acquisition = DataAcquisition(board_num, find_device, rate, dur, save_dir)
    data_acquisition.setup()

    start_pos = int(input("Enter the start position: "))
    end_pos = int(input("Enter the end position: "))
    try:
        data_acquisition.acquire_data_range(start_pos, end_pos)
        data_acquisition.to_csv()
    except KeyboardInterrupt:
        data_acquisition.stop()

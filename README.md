# MCCDAQ data acquisition

<img src="https://img.shields.io/pypi/v/E1608?style=flat-square"/> <img src="https://img.shields.io/pypi/format/E1608?style=flat-square"/> <img src="https://img.shields.io/github/languages/top/mlavvaf/MCCDAQ?style=flat-square"/>
<img src="https://img.shields.io/github/languages/code-size/mlavvaf/MCCDAQ?style=flat-square"/> <img src="https://img.shields.io/pypi/l/E1608?style=flat-square"/> <img src="https://img.shields.io/github/last-commit/mlavvaf/MCCDAQ?style=flat-square"/>

Take data from the MCCDAQ device 

Example 

```python 
from E1608 import E1608
import time

# using 3 channels which we will name ch1, ch2, and ch3
daq = E1608(board_num=0, channels={i:f'ch{i}' for i in range(3)})

# run for 5 seconds
daq.start()
time.sleep(5)
daq.stop()

# draw the results
daq.df.plot()
```

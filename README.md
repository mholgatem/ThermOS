[<img src="../gh-pages/images/banner.jpg">](https://mholgatem.github.io/ThermOS/)

## Setup
### [`Check out the full setup instructions here`](https://mholgatem.github.io/ThermOS/setup)

This thermostat requires the use of a **DS18B20** temperature sensor. **An alternative sensor can be used, but the getIndoorTemp.py file will need to be modified to gather and return the correct data.** I may at some point add the option to use a DHT-22 (combo temp/humidity sensor); but this is adequate for now. 

### -DS18B20-
Your ***DATA*** line needs to be connected to your ***VDD/POWER*** line with a ***4.7K ohm resistor***<br>
Then do the following:<br>
***DATA* on gpio 4 (*physical pin 7*)<br>
*VDD/POWER* on 5v rail (*physical pin 2*)<br>
*GROUND* on any ground pin (*physical pin 6*)**

Next, enable the 1-wire interface.<br>
This can be done by adding the line<br>
**dtoverlay=w1-gpio**<br>
to **/boot/config.txt**<br>
     *-or-*<br>
by using an up-to-date **raspi-config** (Advanced Options -> 1-Wire)

Reboot and your temperature sensor is good to go.

### -SOFTWARE-
On a fresh Raspbian Jessie image (full or lite)<br>

```
cd ~  
git clone https://github.com/mholgatem/ThermOS  
cd ~/ThermOS  
sudo bash install.sh
```
On a computer or smartphone, ***navigate to the ip address of your raspberry pi to finish setup***.

## Credits
ThermOS started life as [Rubustat by Wyatt Winters](https://github.com/wywin/Rubustat) and quickly took on a life of it's own; but there are still a few bits of code left over from those early days.

The forecast api is [powered by Dark Sky](https://darksky.net/poweredby/)

The following icons came from [thenounproject.com](https://thenounproject.com)<br>
*"Folder"* (logs icon) by **Oliviu Stoian**<br>
*"Air Conditioner"* (system icon) by **Aaron K. Kim**<br>
*"Computer Fan"* (fan icon) by **Creative Stall**<br>
*"Thermometer"* (hold icon) by **icon 54**<br>
*"Wrench"* (settings icon) by **useiconic.com**<br>
*"Calendar"* (schedule icon) by **To Uyen**<br>
*"Flame"* (heat icon) by **Nadav Barkan**<br>
*"Snowflake"* (ac icon) by **Dilon Choudry**<br>
*"Meter"* (Favicon) by **kiddo**<br>


*This application is free, without restriction, or warranty.<br>
Don't sue me bro!*

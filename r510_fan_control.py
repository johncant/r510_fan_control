#!usr/bin/env python

import argparse
import json
import logging
import re
import subprocess
from datetime import datetime
from itertools import islice
from json import JSONDecodeError
from time import sleep


class R510FanControlError(ValueError):
    pass


def get_fan_sensor_ids():
    def raise_on_unexpected_result_from_ipmitool():
        raise R510FanControlError(
            "Please make sure `ipmitool -c sdr elist "
            "succeeds and returns comma separated values"
        )
    try:
        proc = subprocess.run(
            ["ipmitool", "sdr", "elist"],
            capture_output=True
        )
        proc.check_returncode()
        lines = proc.stdout.decode('utf-8').split("\n")
        values = [
            [v.strip() for v in line.split("|")]
            for line in lines
            if line
        ]

    except (OSError, subprocess.CalledProcessError):
        raise_on_unexpected_result_from_ipmitool()

    if len(lines) == 0:
        raise R10FanControlError("Did not find any fans using "
                                 "`ipmitool -c sdr elist`")

    # Filter to fans, parse hex, return not-df
    return [
        [
            name,
            int(re.sub('h$', '', id_), 16)
        ]
        for name, id_, *_ in values
        if name.startswith('FAN')
    ]


def get_ambient_temp():
    def raise_on_unexpected_result_from_ipmitool():
        raise R510FanControlError(
            "Please make sure `ipmitool sdr get \"Ambient Temp\" -c "
            "succeeds and returns 18 comma separated values"
        )

    try:
        proc = subprocess.run(
            ["ipmitool", "sdr", "get", "Ambient Temp", "-c"],
            capture_output=True
        )
        proc.check_returncode()
        values = proc.stdout.decode('utf-8').split(",")

    except (OSError, subprocess.CalledProcessError):
        raise_on_unexpected_result_from_ipmitool()

    if len(values) < 18:
        raise_on_unexpected_result_from_ipmitool()

    return float(values[1])


def set_fan_speed(fan_id, pct):
    pct = int(pct)
    try:
        # This command works
        proc = subprocess.run([
            "ipmitool",
            "raw",
            "0x30",
            "0x30",
            "0x01",
            "0x00",
        ], capture_output=True)
        proc.check_returncode()
    except (OSError, subprocess.CalledProcessError):
        import pdb; pdb.set_trace()
        raise R510FanControlError(
            "Command `ipmitool raw 0x30 <sensor_id> 0x01 0x00 failed`"
        )

    try:
        # This command fails but achieves the correct result anyway
        proc = subprocess.run([
            "ipmitool",
            "raw",
            "0x30",
            "0x30",
            "0x02",
            "0x%02x" % fan_id,
            "0x%02x" % pct
        ], capture_output=True)
    except OSError:
        raise R510FanControlError(
            "Command `ipmitool raw 0x30 <sensor_id> 0x02 0xff <pct>` failed"
        )

    expected_failure = (
        "Unable to send RAW command "
        "(channel=0x0 netfn=0x30 lun=0x0 cmd=0x30 rsp=0xcc)"
        ": Invalid data field in request"
    )

    output = proc.stderr.decode("utf-8").strip()
#    if expected_failure not in output:
#        raise R510FanControlError(
#            "Command `ipmitool raw 0x30 0x30 0x02 <fan_id> <pct>` normally "
#            "fails in a specific way, except the output was %s" % output
#        )

    # Fan speed should now be set
    return


def set_fan_speeds(n_fans, f):

    # TODO - establish relationship between number passed to fan control ipmi and fan sensor. Via documented way, not experimentally
    #n_fans = len(fans)

    # Distribute speed in a round robin manner
    total_speed = f*n_fans*100

    base_speed, n_fast = divmod(total_speed, n_fans)

    fast_speed = min(base_speed+1, 100)

    for i in range(n_fans):

        speed = fast_speed if i < n_fast else base_speed

        logging.info("Setting fan %d of %d to %d%%" % (i, n_fans, speed))
        set_fan_speed(i, speed)


def unpack_sensors_temp_dict(tempdict, subfeatures):
    k1, = list(islice(tempdict.keys(), 1))

    # The words here are technically called subfeatures
    # https://github.com/lm-sensors/lm-sensors/blob/master/lib/sensors.h
    # No need to include everything for just R510
    name = re.sub("_(input|max|crit|crit_alarm)$", "", k1)

    assert name != k1, "Could not determine sensor name from %s" % k1

    keys = [
        "%s_%s" % (name, subfeature)
        for subfeature in subfeatures
    ]

    return [
        name,
        *[
            float(number)
            for k in keys
            for number in [tempdict.get(k, None)]
        ]
    ]


def get_cpu_temps():

    try:
        sensors_process = subprocess.run(["sensors", "-j"], capture_output=True)
        sensors_process.check_returncode()
        temps = json.loads(sensors_process.stdout.decode('utf-8'))
    except (OSError, subprocess.CalledProcessError, JSONDecodeError):
        raise R510FanControlError(
            "Please check that lm-sensors is installed and that `sensors -j`"
            "runs and returns valid json."
        )

    # Convert temps to pandas-like dataframe, except we can't expect pandas
    # to be intalled

    temps = [
        [
            toplevel,
            toplevel_dict["Adapter"],
            item,
            *unpack_sensors_temp_dict(tempdict, ["input", "max", "crit"])
        ]
        for toplevel, toplevel_dict in temps.items()
        for item, tempdict in toplevel_dict.items()
        if item != "Adapter"
    ]

    return temps


def main():
    parser = argparse.ArgumentParser(
        prog="r510_fan_control",
        description="Adjust fan speed on Dell Poweredge R510",
    )

    g = parser.add_mutually_exclusive_group(required=False)
    g.add_argument("-d", "--daemon", action="store_true")
    g.add_argument("-t", "--tick", action="store_true")

    args = parser.parse_args()

    if args.daemon:
        daemon(poll_freq=2)

    elif args.tick:
        tick()


def daemon(poll_freq):

    last_tick_time = datetime.utcnow()

    while(True):
        #try:
        tick()
        #except R510FanControlError:
        #    pass

        # This will not result in a perfect constant frequency, but that's
        # totally fine
        sleep_start_time = datetime.utcnow()

        # Time taken for `tick` in seconds
        control_time_s = (sleep_start_time - last_tick_time).total_seconds()

        # Time needed for sleep
        sleep_time_s = max(0, poll_freq - control_time_s)

        logging.debug("Tick took %.2fs" % control_time_s)
        logging.debug("Sleeping for %.2fs" % sleep_time_s)
        sleep(sleep_time_s)

        last_tick_time = datetime.utcnow()


def choose_fan_speed(temps):
    lowest_crit = min([row[-1] for row in temps])
    lowest_max = min([row[-2] for row in temps])
    max_tolerable_temp = min([lowest_crit, lowest_max]) - 15.0

    min_fan_temp = max_tolerable_temp - 25.0

    # Select fan speed based on temperature in range.
    # Don't care about ambient. Yet.
    # Use highest CPU temp

    f = max([
        (row[-3] - min_fan_temp)/
        (max_tolerable_temp - min_fan_temp)
        for row in temps
    ])

    # Clamp f
    f = max(min(f, 1), 0)

    return f


def tick():

    temps = get_cpu_temps()

    f = choose_fan_speed(temps)

    set_fan_speeds(4, f) # 4 fans, can be controlled, but 5 are reported


if __name__ == "__main__":
    main()

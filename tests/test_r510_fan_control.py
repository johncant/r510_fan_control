import json
from unittest.mock import call

from pytest import fixture

from r510_fan_control import (choose_fan_speed, get_cpu_temps, set_fan_speed,
                              set_fan_speeds, tick)


@fixture
def sensors_command(fp):
    fp.register(["sensors", "-j"], stdout=json.dumps({
        "bla": {
            "Adapter": "foo",
            "baz": {
                "temp1_input": 45.000,
                "temp1_max": 80.000,
                "temp1_crit": 90.000
            }
        }
    }))


@fixture
def ipmitool_command(fp):
    def ipmitool_callback(process):
        pass
    for i in range(8):
        fp.register(["ipmitool", "raw", fp.any()], callback=ipmitool_callback)
#    fp.keep_last_process(True)

@fixture
def cli_utils(sensors_command, ipmitool_command):
    pass


def test_smoke_test_tick_fn(cli_utils):
    tick()


def test_set_fan_speed(fp, ipmitool_command):

    set_fan_speed(3, 83)
    assert len(fp.calls) == 2

    assert fp.calls[0] == [
        "ipmitool", "raw", "0x30", "0x30", "0x01", "0x00"
    ]
    assert fp.calls[1] == [
        "ipmitool", "raw", "0x30", "0x30", "0x02", "0x03", "0x53"
    ]

def test_set_fan_speeds(fp, mocker):

    sfs = mocker.patch("r510_fan_control.set_fan_speed")
    set_fan_speeds(2, 0.505)

    assert sfs.call_count == 2
    sfs.assert_has_calls([call(0, 51), call(1, 50)])


def test_get_cpu_temps(sensors_command):
    temps = get_cpu_temps()
    assert temps == [[
        "bla", "foo", "baz", "temp1", 45.0, 80.0, 90.0
    ]]

def test_choose_fan_speed():

    def gen_temps(input_temp, max_temp, crit_temp):
        return [[
            "bla", "foo", "baz", "temp1",
            input_temp, max_temp, crit_temp
        ]]

    # Temp is 1 degree below max. FANS AT FULL SPEED!!!
    assert choose_fan_speed(gen_temps(79.0, 80.0, 90.0)) == 1.0

    # Summer room temp. We want the fans quiet
    assert choose_fan_speed(gen_temps(38.0, 80.0, 90.0)) == 0.0

    # Somewhere in the middle, but agnostic to actual value
    mid_range_f = choose_fan_speed(gen_temps(60.0, 80.0, 90.0))

    assert mid_range_f > 0.0
    assert mid_range_f < 1.0


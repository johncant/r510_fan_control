# Fan control for Dell Poweredge R510

I use this server in my house, and want to minimize noise, while not allowing the server to overheat.

# Fan control ipmi commands

[https://gist.github.com/ODumpling/46c5d70fa545994a3168115a7e8c3fb0](https://gist.github.com/ODumpling/46c5d70fa545994a3168115a7e8c3fb0)

Unable to find simple documentation for these through googling.

In the command

```
ipmitool raw 0x30 0x30 0x02 0xff 0x64
```

the 0xff means "all fans". Passing 0x00, 0x01, 0x02 etc. specifies an individual fan. However, it's not clear how these relate to the fan sensors returned via `ipmitool sdr`.

# Unused info

Fan sensor ids, fan speeds, ambient temperature

# Design

No system-level python dependencies.

Uses existing command line tools to interrogate sensors and ipmi


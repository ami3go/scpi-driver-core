# Pre-Run Safety Checklist

- [ ] Exact N83624 model and firmware recorded.
- [ ] Correct channel and fixture wiring verified.
- [ ] DUT voltage/current/power ratings verified.
- [ ] Driver software limits entered from approved values.
- [ ] Independent DMM/DAQ connected when required.
- [ ] Emergency isolation is accessible.
- [ ] Fusing/current limiting is installed.
- [ ] Robot suite has explicit safe teardown.
- [ ] Raw SCPI is disabled unless the test specifically requires it.
- [ ] UDP is not used for critical control unless qualified.
- [ ] Output is configured while off, then explicitly armed.
- [ ] Audit and Robot output directories are writable.

# pcavatm2las_alpha.py
# script looks at the FEH CAST phase shifter value also the ATM value
# and apply the mirror value to the FS11 drift correction PV 

import epics as epics
import numpy as np
import time as time
import datetime

# source /reg/g/pcds/engineering_tools/xpp/scripts/pcds_conda

FS11_DC_sw_PV  = 'LAS:FS11:VIT:TT_DRIFT_ENABLE'  # Put 0 for disable, put 1 for enable
FS11_DC_val_PV = 'LAS:FS11:VIT:matlab:04'        # Drift correct value in ns
FS11_ATM_PV  = 'XPP:TIMETOOL:TTALL'        # Waveform PV for reading ATM
HXR_PCAV_PV0 = 'SIOC:UNDH:PT01:0:TIME0'     # EGU in ps
HXR_PCAV_PV1 = 'SIOC:UNDH:PT01:0:TIME1'
HXR_CAST_PS_PV_W = 'LAS:UND:MMS:02'         # EGU in ps
HXR_CAST_PS_PV_R = 'LAS:UND:MMS:02.RBV'
SXR_PCAV_PV0 = 'SIOC:UNDS:PT01:0:TIME0'
SXR_PCAV_PV1 = 'SIOC:UNDS:PT01:0:TIME1'
XPP_LAS_TT_PV = 'LAS:FS11:VIT:FS_TGT_TIME'  # EGU in ns

# PCAV/CAST feed forward variables 
cast_avg_n  = 20    # n sample moving average
time_err_th = 50    # pcav err threshold in fs
time_err_ary = 0 
time_err_prev = 0
motr_step_cntr = 0  # counter for how many time the phase "motor" has moved in unit of time_err_th
motr_step_diff_mag = 0 
motr_step_diff_dir = 0 
cntr = 0

# PCAV0_setpoint = epics.caget(HXR_PCAV_PV0)
# PCAV1_setpoint = epics.caget(HXR_PCAV_PV1)
HXR_cast_iqs_sp = epics.caget(HXR_CAST_PS_PV_R)

# ATM Feedback variables
atm_avg_n = cast_avg_n
atm_val_ary = np.zeros(cast_avg_n)
ttamp_th = 0.05
ipm2_th = 3000
ttfwhm_hi = 130
ttfwhm_lo = 70
ATM_wf_val = epics.caget(FS11_ATM_PV)
ATM_pos = ATM_wf_val[0]
ATM_val = ATM_wf_val[1]
ATM_amp = ATM_wf_val[2]
ATM_nxt_amp = ATM_wf_val[3]
ATM_ref_amp = ATM_wf_val[4]
ATM_fwhm = ATM_wf_val[5]
atm_pm_step = 0

print('Controller running')
while True:
    print('//////////////////////////////////////////////////////////////////')
    print('Counter val: ' + str(cntr))
    # PCAV0_Val_tmp = epics.caget(HXR_PCAV_PV0)
    cast_val_tmp = epics.caget(HXR_CAST_PS_PV_R)
    time_err = np.around((cast_val_tmp - HXR_cast_iqs_sp), decimals=6)
    time_err_delta = time_err - time_err_prev
    print(cast_val_tmp)
    print(time_err)
    # Getting ATM reading
    atm_wf_tmp = epics.caget(FS11_ATM_PV)
    atm_pos = atm_wf_tmp[0]
    atm_val = atm_wf_tmp[1]
    atm_amp = atm_wf_tmp[2]
    atm_nxt_amp = atm_wf_tmp[3]
    atm_ref_amp = atm_wf_tmp[4]
    atm_fwhm = atm_wf_tmp[5]
    if(cntr%10 == 0):
        print(atm_wf_tmp)
    # Testing if the ATM readback is valid parameter from Takahiro
    if (atm_amp > ttamp_th)and(atm_nxt_amp > ipm2_th)and(atm_fwhm < ttfwhm_hi)and(atm_fwhm >  ttfwhm_lo)and(atm_val != atm_val_ary[-1,]):
        tt_ok = 1
        print('!!!!!!!!!!Good ATM reading!!!!!!!!!!')
    else:
        tt_ok = 0
        print('##########Bad ATM reading###########')
    cntr = cntr + 1       

    # Filling the running avg array
    if cntr == 0:
        time_err_ary = time_err
        if tt_ok:
            atm_val_ary = atm_val
    elif (cntr >= cast_avg_n):
        if np.abs(time_err_delta) < (0.100):
            time_err_ary = np.delete(time_err_ary, 0)
            time_err_ary = np.append(time_err_ary, time_err)
        if tt_ok:
            atm_val_ary = np.delete(atm_val_ary, 0)
            atm_val_ary = np.append(atm_val_ary,atm_val)
    else:
        time_err_ary = np.append(time_err_ary, time_err)
        if tt_ok:
            atm_val_ary = np.append(atm_val_ary,atm_val)
    time_err_mean = np.mean(time_err_ary)
    time_err_mean_fs = np.around(np.multiply(time_err_mean, 1000), 3)
    # average and convert to fs
    atm_ary_mean  = np.mean(atm_val_ary)
    atm_ary_mean_fs = np.around(np.multiply(atm_ary_mean, 1000), 3)

    # Decide which feedback to use
    if tt_ok:
        pm_step = -1*np.trunc(np.true_divide(atm_ary_mean_fs, time_err_th))
    else:
        pm_step = -1*np.trunc(np.true_divide(time_err_mean_fs, time_err_th))

    print('phase motor step: ' + str(pm_step))
    current_DC_val = epics.caget(FS11_DC_val_PV)
    if pm_step != motr_step_cntr:
        print('///////////////moving drift compensation/////////////')
        motr_step_diff = pm_step - motr_step_cntr
        motr_step_diff_mag = np.abs(motr_step_diff)
        motr_step_diff_dir = np.sign(motr_step_diff)        
        print('current drift comp val = ' + str(current_DC_val) + '\n')
        pm_val = np.multiply(pm_step, time_err_th)
        new_DC_val = current_DC_val + np.true_divide(pm_val, 1e6)
        print('epics.caput(FS11_DC_val_PV, new_DC_val)')
        # epics.caput(FS11_DC_val_PV, new_DC_val)
        motr_step_cntr = pm_step
        print('move time by: ' + str(pm_val))
        print('pm delta: ' + str(motr_step_diff))
    print('CAST err delta: ' + str(np.around(time_err_delta, 3)) + 'ps')
    print('motor steps: ' + str(pm_step))
    print('current pm cntr: ' + str(motr_step_cntr))
    print('current DC val: ' + str(current_DC_val))
    print('\n\n')
    print(str(cast_avg_n) + ' sample moving average cast err: ' + str(time_err_mean_fs) + 'fs')
    print('cast err array: ')
    print(time_err_ary)
    print(str(cast_avg_n) + ' sample moving average atm err: ' + str(atm_ary_mean_fs) + 'fs')
    print('atm err array: ')
    print(atm_val_ary)    
    time_err_prev = time_err
    cntr = cntr + 1
    time.sleep(1)
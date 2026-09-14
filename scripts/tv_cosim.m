function tv_cosim(workdir, solver_matlab_dir, tstop, dt)
% TV_COSIM Torque-vectoring co-simulation demo (4-motor EV, zero steering).
%
%   tv_cosim('<workdir>', '<PROG>\Programs\solvers\Matlab')
%
% Expects <workdir>/simfile.sim with 4 torque imports (IMP_M_MOTOR_CMD_*)
% and 4 exports (Vx, AVz, Yo, Steer_SW) -- see examples/torque_vectoring.py.
% Controller: total wheel torque from PI on speed error; differential torque
% from PI on yaw-rate error. Steering stays at ZERO -- all yaw is generated
% by left/right torque vectoring. Writes <workdir>/cosim_results.csv
% (t, Vx km/h, AVz deg/s, Yo m, Steer_SW deg, T_left, T_right).
if nargin < 2
    solver_matlab_dir = 'C:/CarSim/CarSim2024.0_Prog/Programs/solvers/Matlab';
end
v_target = 50 / 3.6;   % m/s
r_target = 0.06;       % rad/s, generated purely by torque vectoring
Kp_v = 60;  Ki_v = 15;    % N.m (total, at wheels) per m/s
Kp_r = 3000; Ki_r = 5000; % N.m (differential) per rad/s
T_tot_max = 2400;         % N.m total
dT_max = 900;             % N.m left-right differential
Tw_max = 580;             % N.m per wheel
if nargin < 3, tstop = 30; end
if nargin < 4, dt = 0.001; end
try
    addpath(solver_matlab_dir);
    cd(workdir);
    load_system(fullfile(solver_matlab_dir, 'Solver_SF.slx'));
    mdl = 'carsim_tv';
    if bdIsLoaded(mdl), close_system(mdl, 0); end
    if exist([mdl '.slx'], 'file'), delete([mdl '.slx']); end
    new_system(mdl);

    add_block('Solver_SF/CarSim S-Function', [mdl '/CarSim'], ...
        'SIMFILE', 'simfile.sim', 'Position', [560 100 690 160]);

    % ---- speed loop: v_target - Vx(m/s) -> PI -> T_tot
    add_block('simulink/Sources/Constant', [mdl '/v_target'], ...
        'Value', num2str(v_target), 'Position', [30 30 85 70]);
    add_block('simulink/Math Operations/Gain', [mdl '/kms2ms'], ...
        'Gain', '0.277778', 'Position', [120 120 170 150]); % Vx km/h -> m/s
    add_block('simulink/Math Operations/Sum', [mdl '/verr'], ...
        'Inputs', '+-', 'Position', [210 60 240 90]);
    add_block('simulink/Math Operations/Gain', [mdl '/Kp_v'], ...
        'Gain', num2str(Kp_v), 'Position', [280 40 310 70]);
    add_block('simulink/Discrete/Discrete-Time Integrator', [mdl '/iv'], ...
        'SampleTime', num2str(dt, 17), 'Position', [280 95 310 125]);
    add_block('simulink/Math Operations/Gain', [mdl '/Ki_v'], ...
        'Gain', num2str(Ki_v), 'Position', [320 95 350 125]);
    add_block('simulink/Math Operations/Sum', [mdl '/vpi'], ...
        'Inputs', '++', 'Position', [380 60 410 90]);
    add_block('simulink/Discontinuities/Saturation', [mdl '/Ttot_sat'], ...
        'UpperLimit', num2str(T_tot_max), 'LowerLimit', '0', ...
        'Position', [440 60 470 90]);

    % ---- yaw loop: r_target - AVz(rad/s) -> PI -> dT
    add_block('simulink/Sources/Constant', [mdl '/r_target'], ...
        'Value', num2str(r_target), 'Position', [30 220 85 260]);
    add_block('simulink/Math Operations/Gain', [mdl '/d2r'], ...
        'Gain', '0.0174533', 'Position', [120 310 170 340]); % AVz deg/s->rad/s
    add_block('simulink/Math Operations/Sum', [mdl '/rerr'], ...
        'Inputs', '+-', 'Position', [210 250 240 280]);
    add_block('simulink/Math Operations/Gain', [mdl '/Kp_r'], ...
        'Gain', num2str(Kp_r), 'Position', [280 230 310 260]);
    add_block('simulink/Discrete/Discrete-Time Integrator', [mdl '/ir'], ...
        'SampleTime', num2str(dt, 17), 'Position', [280 285 310 315]);
    add_block('simulink/Math Operations/Gain', [mdl '/Ki_r'], ...
        'Gain', num2str(Ki_r), 'Position', [320 285 350 315]);
    add_block('simulink/Math Operations/Sum', [mdl '/rpi'], ...
        'Inputs', '++', 'Position', [380 250 410 280]);
    add_block('simulink/Discontinuities/Saturation', [mdl '/dT_sat'], ...
        'UpperLimit', num2str(dT_max), 'LowerLimit', num2str(-dT_max), ...
        'Position', [440 250 470 280]);

    % ---- split: T_left = Ttot/4 - dT/2 ; T_right = Ttot/4 + dT/2
    add_block('simulink/Math Operations/Gain', [mdl '/q'], ...
        'Gain', '0.25', 'Position', [500 60 530 90]);
    add_block('simulink/Math Operations/Gain', [mdl '/h'], ...
        'Gain', '0.5', 'Position', [500 250 530 280]);
    add_block('simulink/Math Operations/Sum', [mdl '/TL'], ...
        'Inputs', '+-', 'Position', [560 40 590 70]);
    add_block('simulink/Math Operations/Sum', [mdl '/TR'], ...
        'Inputs', '++', 'Position', [560 260 590 290]);
    add_block('simulink/Discontinuities/Saturation', [mdl '/TLsat'], ...
        'UpperLimit', num2str(Tw_max), 'LowerLimit', num2str(-Tw_max), ...
        'Position', [620 40 650 70]);
    add_block('simulink/Discontinuities/Saturation', [mdl '/TRsat'], ...
        'UpperLimit', num2str(Tw_max), 'LowerLimit', num2str(-Tw_max), ...
        'Position', [620 260 650 290]);
    % feed both axles: import order D1_L, D1_R, D2_L, D2_R
    add_block('simulink/Signal Routing/Mux', [mdl '/mux4'], ...
        'Inputs', '4', 'Position', [740 100 745 260]);

    % ---- exports: [Vx(km/h) AVz(deg/s) Yo(m) Steer_SW(deg)]
    add_block('simulink/Signal Routing/Demux', [mdl '/exports'], ...
        'Outputs', '4', 'Position', [790 95 795 175]);
    names = {'Vx_kmh', 'AVz_degs', 'Yo_m', 'SteerSW_deg'};
    for k = 1:4
        add_block('simulink/Sinks/To Workspace', [mdl '/ts_' names{k}], ...
            'VariableName', ['ts_' names{k}], 'SaveFormat', 'Timeseries', ...
            'Position', [850 (k - 1) * 45 + 40 910 (k - 1) * 45 + 70]);
        add_line(mdl, ['exports/' num2str(k)], ['ts_' names{k} '/1'], ...
            'autorouting', 'on');
    end
    add_block('simulink/Sinks/To Workspace', [mdl '/ts_TL'], ...
        'VariableName', 'ts_TL', 'SaveFormat', 'Timeseries', ...
        'Position', [740 320 800 350]);
    add_block('simulink/Sinks/To Workspace', [mdl '/ts_TR'], ...
        'VariableName', 'ts_TR', 'SaveFormat', 'Timeseries', ...
        'Position', [740 360 800 390]);

    % wiring
    add_line(mdl, 'v_target/1', 'verr/1', 'autorouting', 'on');
    add_line(mdl, 'kms2ms/1', 'verr/2', 'autorouting', 'on');
    add_line(mdl, 'verr/1', 'Kp_v/1', 'autorouting', 'on');
    add_line(mdl, 'verr/1', 'iv/1', 'autorouting', 'on');
    add_line(mdl, 'iv/1', 'Ki_v/1', 'autorouting', 'on');
    add_line(mdl, 'Kp_v/1', 'vpi/1', 'autorouting', 'on');
    add_line(mdl, 'Ki_v/1', 'vpi/2', 'autorouting', 'on');
    add_line(mdl, 'vpi/1', 'Ttot_sat/1', 'autorouting', 'on');
    add_line(mdl, 'Ttot_sat/1', 'q/1', 'autorouting', 'on');
    add_line(mdl, 'q/1', 'TL/1', 'autorouting', 'on');
    add_line(mdl, 'q/1', 'TR/1', 'autorouting', 'on');
    add_line(mdl, 'r_target/1', 'rerr/1', 'autorouting', 'on');
    add_line(mdl, 'd2r/1', 'rerr/2', 'autorouting', 'on');
    add_line(mdl, 'rerr/1', 'Kp_r/1', 'autorouting', 'on');
    add_line(mdl, 'rerr/1', 'ir/1', 'autorouting', 'on');
    add_line(mdl, 'ir/1', 'Ki_r/1', 'autorouting', 'on');
    add_line(mdl, 'Kp_r/1', 'rpi/1', 'autorouting', 'on');
    add_line(mdl, 'Ki_r/1', 'rpi/2', 'autorouting', 'on');
    add_line(mdl, 'rpi/1', 'dT_sat/1', 'autorouting', 'on');
    add_line(mdl, 'dT_sat/1', 'h/1', 'autorouting', 'on');
    add_line(mdl, 'h/1', 'TL/2', 'autorouting', 'on');
    add_line(mdl, 'h/1', 'TR/2', 'autorouting', 'on');
    add_line(mdl, 'TL/1', 'TLsat/1', 'autorouting', 'on');
    add_line(mdl, 'TR/1', 'TRsat/1', 'autorouting', 'on');
    add_line(mdl, 'TLsat/1', 'mux4/1', 'autorouting', 'on');
    add_line(mdl, 'TRsat/1', 'mux4/2', 'autorouting', 'on');
    add_line(mdl, 'TLsat/1', 'mux4/3', 'autorouting', 'on');
    add_line(mdl, 'TRsat/1', 'mux4/4', 'autorouting', 'on');
    add_line(mdl, 'mux4/1', 'CarSim/1', 'autorouting', 'on');
    add_line(mdl, 'CarSim/1', 'exports/1', 'autorouting', 'on');
    add_line(mdl, 'exports/1', 'kms2ms/1', 'autorouting', 'on');
    add_line(mdl, 'exports/2', 'd2r/1', 'autorouting', 'on');
    add_line(mdl, 'TLsat/1', 'ts_TL/1', 'autorouting', 'on');
    add_line(mdl, 'TRsat/1', 'ts_TR/1', 'autorouting', 'on');

    set_param(mdl, 'StopTime', num2str(tstop), 'SolverType', 'Fixed-step', ...
        'Solver', 'ode1', 'FixedStep', num2str(dt, 17));
    save_system(mdl);
    fprintf('model built, running...\n');
    out = sim(mdl);

    t = double(out.ts_AVz_degs.Time);   % numeric already -- never seconds()!
    M = [t, out.ts_Vx_kmh.Data(:), out.ts_AVz_degs.Data(:), ...
         out.ts_Yo_m.Data(:), out.ts_SteerSW_deg.Data(:), ...
         out.ts_TL.Data(:), out.ts_TR.Data(:)];
    writematrix(M, 'cosim_results.csv');
    fprintf(['DONE rows=%d final_AVz=%.4f deg/s (target %.4f) ' ...
             'Steer_SW=%.2f deg\n'], size(M, 1), M(end, 3), ...
            r_target / 0.0174533, max(abs(M(:, 5))));
catch e
    fprintf(2, 'ERROR: %s\n', getReport(e, 'basic'));
    exit(1);
end
end

function cosim_model(workdir, solver_matlab_dir, tstop, dt)
% COsim_MODEL Build + run a CarSim/Simulink co-simulation model headless.
%
%   cosim_model('<workdir>', '<PROG>\Programs\solvers\Matlab')
%
% Expects <workdir> to already contain a co-sim "simfile.sim" (PORTS_IMP 1,1 /
% PORTS_EXP 1,5 — see the carsim-guide skill). Builds a model with the CarSim
% S-Function block plus a PI yaw-rate controller on export #2 (AVz, deg/s),
% runs 30 s fixed-step at 1 kHz, and writes <workdir>/cosim_results.csv
% (columns: t, Vx km/h, AVz deg/s, Ay g, Yo m, Steer_SW deg, steer_cmd deg).
%
% Run headless:
%   matlab -batch "cosim_model('C:/work/demo', 'C:/CarSim/.../solvers/Matlab')"
if nargin < 2
    solver_matlab_dir = 'C:/CarSim/CarSim2024.0_Prog/Programs/solvers/Matlab';
end
r_target = 0.15;   % rad/s
Kp = 600;          % deg per rad/s
Ki = 1200;         % deg per rad
sat = 120;         % deg
if nargin < 3, tstop = 30; end
if nargin < 4, dt = 0.001; end
try
    addpath(solver_matlab_dir);
    cd(workdir);
    load_system(fullfile(solver_matlab_dir, 'Solver_SF.slx'));
    mdl = 'carsim_cosim';
    if bdIsLoaded(mdl), close_system(mdl, 0); end
    if exist([mdl '.slx'], 'file'), delete([mdl '.slx']); end
    new_system(mdl);

    % CarSim solver: official library block, mask param SIMFILE (relative to cwd)
    add_block('Solver_SF/CarSim S-Function', [mdl '/CarSim'], ...
        'SIMFILE', 'simfile.sim', 'Position', [340 100 470 160]);
    % PI controller on yaw-rate error; export #2 = AVz [deg/s]
    add_block('simulink/Sources/Constant', [mdl '/r_target'], ...
        'Value', num2str(r_target), 'Position', [40 40 90 80]);
    add_block('simulink/Math Operations/Sum', [mdl '/err'], ...
        'Inputs', '+-', 'Position', [140 55 170 85]);
    add_block('simulink/Math Operations/Gain', [mdl '/Kp'], ...
        'Gain', num2str(Kp), 'Position', [215 40 245 70]);
    add_block('simulink/Discrete/Discrete-Time Integrator', [mdl '/intg'], ...
        'SampleTime', num2str(dt, 17), 'Position', [215 95 245 125]);
    add_block('simulink/Math Operations/Gain', [mdl '/Ki'], ...
        'Gain', num2str(Ki), 'Position', [255 95 285 125]);
    add_block('simulink/Math Operations/Sum', [mdl '/pi_sum'], ...
        'Inputs', '++', 'Position', [300 60 330 90]);
    add_block('simulink/Discontinuities/Saturation', [mdl '/sat'], ...
        'UpperLimit', num2str(sat), 'LowerLimit', num2str(-sat), ...
        'Position', [350 60 380 90]);
    add_block('simulink/Signal Routing/Demux', [mdl '/exports'], ...
        'Outputs', '5', 'Position', [520 95 525 205]);
    add_block('simulink/Math Operations/Gain', [mdl '/d2r'], ...
        'Gain', '0.0174533', 'Position', [570 130 620 160]);

    names = {'Vx_kmh', 'AVz_degs', 'Ay_g', 'Yo_m', 'SteerSW_deg'};
    for k = 1:5
        add_block('simulink/Sinks/To Workspace', [mdl '/ts_' names{k}], ...
            'VariableName', ['ts_' names{k}], 'SaveFormat', 'Timeseries', ...
            'Position', [660 (k - 1) * 45 + 40 720 (k - 1) * 45 + 70]);
        add_line(mdl, ['exports/' num2str(k)], ['ts_' names{k} '/1'], ...
            'autorouting', 'on');
    end
    add_block('simulink/Sinks/To Workspace', [mdl '/ts_steer_cmd'], ...
        'VariableName', 'ts_steer_cmd', 'SaveFormat', 'Timeseries', ...
        'Position', [200 140 260 170]);

    add_line(mdl, 'r_target/1', 'err/1', 'autorouting', 'on');
    add_line(mdl, 'd2r/1', 'err/2', 'autorouting', 'on');
    add_line(mdl, 'err/1', 'Kp/1', 'autorouting', 'on');
    add_line(mdl, 'err/1', 'intg/1', 'autorouting', 'on');
    add_line(mdl, 'intg/1', 'Ki/1', 'autorouting', 'on');
    add_line(mdl, 'Kp/1', 'pi_sum/1', 'autorouting', 'on');
    add_line(mdl, 'Ki/1', 'pi_sum/2', 'autorouting', 'on');
    add_line(mdl, 'pi_sum/1', 'sat/1', 'autorouting', 'on');
    add_line(mdl, 'sat/1', 'CarSim/1', 'autorouting', 'on');
    add_line(mdl, 'sat/1', 'ts_steer_cmd/1', 'autorouting', 'on');
    add_line(mdl, 'CarSim/1', 'exports/1', 'autorouting', 'on');
    add_line(mdl, 'exports/2', 'd2r/1', 'autorouting', 'on');

    set_param(mdl, 'StopTime', num2str(tstop), 'SolverType', 'Fixed-step', ...
        'Solver', 'ode1', 'FixedStep', num2str(dt, 17));
    save_system(mdl);
    fprintf('model built, running...\n');
    out = sim(mdl);

    t = double(out.ts_AVz_degs.Time);   % Time is already numeric (no seconds()!)
    M = [t, out.ts_Vx_kmh.Data(:), out.ts_AVz_degs.Data(:), ...
         out.ts_Ay_g.Data(:), out.ts_Yo_m.Data(:), ...
         out.ts_SteerSW_deg.Data(:), out.ts_steer_cmd.Data(:)];
    writematrix(M, 'cosim_results.csv');
    fprintf(['DONE rows=%d final_AVz=%.3f deg/s (target %.3f) ' ...
             'max_AVz=%.3f\n'], size(M, 1), M(end, 3), ...
            r_target / 0.0174533, max(abs(M(:, 3))));
catch e
    fprintf(2, 'ERROR: %s\n', getReport(e, 'basic'));
    exit(1);
end
end

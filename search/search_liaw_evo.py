import time
import json
import os
import os.path as osp
from os.path import join as pjoin
from os.path import abspath as apath
import argparse
from itertools import product

import yaml
import numpy as np
import pygmo as pg

from lpf.models import LiawModel
from lpf.initializers import LiawInitializer
from lpf.objectives import ObjectiveFactory as ObjFac
from lpf.search import EvoSearch
from lpf.search.converters import LiawConverter
from lpf.utils import get_module_dpath
from lpf.utils import load_model_dicts



np.seterr(all='raise')


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Parse configruations for searching.')
    parser.add_argument('--config',
                        dest='config',
                        action='store',
                        type=str,
                        help='Designate the file path of configuration file in YAML')

    parser.add_argument('--gpu',
                        dest='gpu',
                        action='store',
                        type=int,
                        help='Designate the gpu device id')

    args = parser.parse_args()
    fpath_config = osp.abspath(args.config)        
            
    with open(fpath_config, "rt") as fin:
        config = yaml.safe_load(fin)

    # Create a search object.
    num_init_pts = config["NUM_INIT_PTS"]

    converter = LiawConverter()
        
    # Create the model.
    dx = float(config["DX"])
    dt = float(config["DT"])
    width = int(config["WIDTH"])
    height = int(config["HEIGHT"])
    thr = float(config["THR"])
    n_iters = int(config["N_ITERS"])
    rtol_early_stop = float(config["RTOL_EARLY_STOP"])

    shape = (height, width)
   
    # Create the objectives.
    objectives = []
    for cfg in config["OBJECTIVES"]:
        obj = cfg[0]
        coeff = float(cfg[1])

        device = "cpu"
        if "cuda" in cfg[2]:
            device = "cuda:%d"%(args.gpu)

        print("[OBJECTIVE DEVICE] %s: %s"%(obj, device))
        
        objectives.append(ObjFac.create(obj, coeff=coeff, device=device))
    # end of for

    # Load ladybird type and the corresponding data.
    # ladybird_type = config["LADYBIRD_TYPE"].lower()
    # dpath_data = pjoin(get_module_dpath("data"), ladybird_type)
    # dpath_template = pjoin(dpath_data, "template")
    # dpath_target = pjoin(dpath_data, "target")
    #
    # fpath_template = pjoin(dpath_template, "ladybird.png")
    # fpath_mask = pjoin(dpath_template, "mask.png")
    
    model = LiawModel(
        width=width,
        height=height,                 
        dx=dx,
        dt=dt,
        n_iters=n_iters,
        num_init_pts=num_init_pts,
        rtol_early_stop=rtol_early_stop,
        device=device
    )
    
    # Load targets.
    targets = config["TARGETS"]
    # ladybird_subtypes = [elem.lower() for elem in ladybird_subtypes]
    # targets = load_targets(dpath_target,
    #                        ladybird_subtypes)

    droot_output = apath(config["DPATH_OUTPUT"])
    search = EvoSearch(config,
                       model,
                       converter,
                       targets,
                       objectives,
                       droot_output)

    prob = pg.problem(search)
    print(prob) 
   
    
    # Create the initial population.
    t_beg = time.time()
    pop_size = int(config["POP_SIZE"])
    pop = pg.population(prob, size=pop_size)
    
    dpath_init_pop = osp.abspath(config["INIT_POP"])
    if dpath_init_pop:
    #
    #     x = np.zeros((10 + 2*num_init_pts,), dtype=np.float64)
    #
    #     for i, fname in enumerate(os.listdir(dpath_init_pop)):
    #         if i == pop_size:
    #             break
    #
    #         if not fname.endswith("json"):
    #             continue
    #
    #         fpath_model = pjoin(dpath_init_pop, fname)
    #
    #         # Load the params.
    #         with open(fpath_model, "rt") as fin:
    #             n2v = json.load(fin)
    #
    #         x[0] = np.log10(n2v["Du"])
    #         x[1] = np.log10(n2v["Dv"])
    #         x[2] = np.log10(n2v["ru"])
    #         x[3] = np.log10(n2v["rv"])
    #         x[4] = np.log10(n2v["k"])
    #         x[5] = np.log10(n2v["su"])
    #         x[6] = np.log10(n2v["sv"])
    #         x[7] = np.log10(n2v["mu"])
    #         x[8] = np.log10(n2v["u0"])
    #         x[9] = np.log10(n2v["v0"])
    #
    #         j = 0
    #         for name, val in n2v.items():
    #             if "init_pts" in name:
    #                 x[10 + 2*j] = int(val[0])
    #                 x[11 + 2*j] = int(val[1])
    #                 j += 1
    #         # end of for
    #
    #         if j == 0: # if there is no initial point.
    #             # rc_product: Production of rows and columns
    #             rc_product = product(np.arange(40, 90, 10),
    #                                  np.arange(10, 110, 20))
    #
    #             for j, (ir, ic) in enumerate(rc_product):
    #                 x[10 + 2*j] = ir
    #                 x[11 + 2*j] = ic
    #             # end of for
    #         # end of if
    #     # end of for

        eval_init_fitness = int(config["EVAL_INIT_FITNESS"])
        for i, fname in enumerate(os.listdir(dpath_init_pop)):

            if eval_init_fitness:
                pop.set_x(i, x)
            elif "fitness" in n2v:
                fitness = float(n2v["fitness"])
                pop.set_xf(i, x, [fitness])
            else:
                raise ValueError("'fitness' should be defined in the JSON file if EVAL_INIT_FITNESS is False.")

        # end of for
    # end of if
    t_end = time.time()
    print("[DURATION OF INITIALIZING POPULATION] %.3f sec."%(t_end - t_beg))
    print(pop)

    # Create an evolutionary algorithm.
    n_procs = int(config["N_PROCS"])
    n_gen = int(config["N_GEN"])

    udi = pg.mp_island()
    udi.resize_pool(n_procs)
    isl = pg.island(algo=pg.sade(gen=1), pop=pop, udi=udi)

    try:
        for i in range(n_gen):
            print(isl)
            t_beg = time.time()
            isl.evolve()
            isl.wait_check()
            t_end = time.time()
            
            print("[EVOLUTION #%d] Best objective: %f (%.3f sec.)"%(i + 1, pop.champion_f[0], t_end - t_beg))

            # Save the best.
            pop = isl.get_population()
            search.save("best", pop.champion_x, generation=i+1, fitness=pop.champion_f[0])

            # Save the population.
            arr_x = pop.get_x()
            arr_f = pop.get_f()
            for j in range(arr_x.shape[0]):
                x = arr_x[j]
                fitness = arr_f[j, 0]
                search.save("pop", x, generation=i+1, fitness=fitness)
        # end of for
    except Exception as err:
        print(err)
        udi.shutdown_pool()

    print("[EVOLUTIONARY SEARH COMPLETED]")
    udi.shutdown_pool()

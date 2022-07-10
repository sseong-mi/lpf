import time
import json
import os.path as osp
from os.path import join as pjoin
from os.path import abspath as apath
from datetime import datetime
import argparse
from itertools import product

import yaml
import numpy as np
import pygmo as pg
import matplotlib.pyplot as plt

from lpf.models import LiawModel
from lpf.initializers import LiawInitializer
from lpf.initializers import InitializerFactory as InitFac
from lpf.objectives import ObjectiveFactory as ObjFac
from lpf.search import RdPde2dSearch
from lpf.utils import get_module_dpath
from lpf.data import load_targets

plt.ioff()
np.seterr(all='raise')


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Parse configruations for searching.')
    parser.add_argument('--config',
                        dest='config',
                        action='store',
                        type=str,
                        help='Designate the file path of configuration file in YAML')

    args = parser.parse_args()
    fpath_config = osp.abspath(args.config)        
            
    with open(fpath_config, "rt") as fin:
        config = yaml.safe_load(fin)

    # Create a search object.
    num_init_pts = config["NUM_INIT_PTS"]

    class LiawModelConverter:
                                            
        def to_params(self, x, params=None):
            """
            Args:
                x: Decision vector of PyGMO
            """
            if params is None:
                params = np.zeros((10,), dtype=np.float64)
            Du = 10 ** x[0]
            Dv = 10 ** x[1]
            ru = 10 ** x[2]
            rv = 10 ** x[3]
            k  = 10 ** x[4]
            su = 10 ** x[5]
            sv = 10 ** x[6]
            mu = 10 ** x[7]
                
            params[0] = Du
            params[1] = Dv
            params[2] = ru
            params[3] = rv
            params[4] = k
            params[5] = su
            params[6] = sv
            params[7] = mu
            
            return params
            
            
        def to_init_states(self, x, init_states=None):    
            if init_states is None:
                init_states = np.zeros((2,), dtype=np.float64)
                
            init_states[0] =  10 ** x[8]  # u0
            init_states[1] = 10 ** x[9]  # v0
            return init_states
        
        def to_init_pts(self, x):            
            ir = np.zeros(num_init_pts, dtype=np.int32)
            ic = np.zeros(num_init_pts, dtype=np.int32)
            
            for i, coord in enumerate(zip(x[10::2], x[11::2])): 
                ir[i] = int(coord[0])
                ic[i] = int(coord[1])
                
            return ir, ic
        
        def to_initializer(self, x):            
            ir_init, ic_init = self.to_init_pts(x)            
            init = LiawInitializer(ir_init=ir_init, ic_init=ic_init)
            return init
                   
            
        
    converter = LiawModelConverter()
        
    # Create the model.
    dx = float(config["DX"])
    dt = float(config["DT"])
    width = int(config["WIDTH"])
    height = int(config["HEIGHT"])
    thr = float(config["THR"])
    n_iters = int(config["N_ITERS"])
    shape = (height, width)
   
    # Create the objectives.
    objectives = []
    for cfg in config["OBJECTIVES"]:
        obj = cfg[0]
        coeff = float(cfg[1])
        device = cfg[2]        
        
        objectives.append(ObjFac.create(obj, coeff=coeff, device=device))
    # end of for

    # Load ladybird type and the corresponding data.
    ladybird_type = config["LADYBIRD_TYPE"].lower()
    dpath_data = pjoin(get_module_dpath("data"), ladybird_type)
    dpath_template = pjoin(dpath_data, "template")
    dpath_target = pjoin(dpath_data, "target")

    fpath_template = pjoin(dpath_template, "ladybird.png")    
    fpath_mask = pjoin(dpath_template, "mask.png")
    
    model = LiawModel(
        width=width,
        height=height,                 
        dx=dx,
        dt=dt,
        n_iters=n_iters,
        num_init_pts=num_init_pts,
        rtol_early_stop=2e-5,
        fpath_template=fpath_template,
        fpath_mask=fpath_mask
    )
    
    # Load targets.
    ladybird_subtypes = config["LADYBIRD_SUBTYPES"]
    ladybird_subtypes = [elem.lower() for elem in ladybird_subtypes]
    targets = load_targets(dpath_target,
                           ladybird_subtypes)

    droot_output = apath(config["DPATH_OUTPUT"])
    search = RdPde2dSearch(config,
                           model,
                           converter,
                           targets,
                           objectives,
                           droot_output)
    prob = pg.problem(search)
    print(prob) 
   
    
    # Create an initial population.
    pop_size = int(config["POP_SIZE"])
    pop = pg.population(prob, size=pop_size)
    
    fpath_initpop = config["INIT_POP"]
    if fpath_initpop:
        fpath_initpop = osp.abspath(fpath_initpop)
        
        if osp.isfile(fpath_initpop):
            with open(fpath_initpop, "rt") as fin:
                print("[INITIAL POPULATION]", fpath_initpop)
                
                list_n2v = json.load(fin)
                
            x = np.zeros((10 + 2*num_init_pts,), dtype=np.float64)
            for i, n2v in enumerate(list_n2v):
                x[0] = np.log10(n2v["Du"])
                x[1] = np.log10(n2v["Dv"])
                x[2] = np.log10(n2v["ru"])
                x[3] = np.log10(n2v["rv"])
                x[4] = np.log10(n2v["k"])
                x[5] = np.log10(n2v["su"])
                x[6] = np.log10(n2v["sv"])
                x[7] = np.log10(n2v["mu"])
                x[8] = np.log10(n2v["u0"])
                x[9] = np.log10(n2v["v0"])
               
               
                j = 0
                for name, val in n2v.items():
                    if "init-pts" in name:
                        x[10 + 2*j] = int(val[0])
                        x[11 + 2*j] = int(val[1])
                        j += 1
                        print(name, (10 + 2*j, 11 + 2*j), val)
                # end of for

                if j == 0:  # if the number of init pts equals to 0.
                    # rc_product: Production of rows and columns
                    rc_product = product(np.arange(40, 90, 10),
                                         np.arange(10, 110, 20))

                    for j, (ir, ic) in enumerate(rc_product):
                        x[10 + 2*j] = ir
                        x[11 + 2*j] = ic
                    # end of for
                
                pop.set_x(i, x)
            # end of for
    
    # Create an algorithm.

    n_proc = int(config["N_PROC"])
    bfe = pg.mp_bfe()
    bfe.init_pool(n_proc)
    
    isl = pg.island(algo=pg.sade(gen=1),
                    pop=pop,                   
                    b=bfe) #, udi=pg.mp_island())
    
    
    num_gen = config["N_GEN"]
    for i in range(num_gen):
        print(isl)
        t_beg = time.time()
        
        isl.evolve()
        pop = isl.get_population()
        
        t_end = time.time()        
        dur = t_end - t_beg
        print("[Evolution #%d] Best objective: %f (%.3f sec.)"%(i + 1, pop.champion_f[0], dur))        
        
        str_now = datetime.now().strftime('%Y%m%d-%H%M%S')
        fpath_model = pjoin(search.dpath_best, "model_%s.json"%(str_now))
        fpath_image = pjoin(search.dpath_best, "image_%s.png"%(str_now))        
        search.save(fpath_model, fpath_image, pop.champion_f[0], pop.champion_x)
    # end of for

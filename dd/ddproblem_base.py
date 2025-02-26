#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Jan  6 11:03:38 2023

@author: ffiguere

This file is part of ddfenics, a FEniCs-based (Model-Free) Data-driven 
Computational Mechanics implementation.

Copyright (c) 2022-2023, Felipe Rocha.
See file LICENSE.txt for license information.
Please report all bugs and problems to <felipe.figueredo-rocha@ec-nantes.fr>, or
<f.rocha.felipe@gmail.com>

"""

import numpy as np
import dolfin as df
import ddfenics as dd 

class DDProblemBase:
    
    def __init__(self, spaces, grad, L, bcs, metric,  
                 form_compiler_parameters = {}, bcsPF = [], is_accelerated = True):
    
        self.Uh, self.Sh = spaces 
        self.metric = metric
        
        self.z_mech = dd.DDState([dd.DDFunction(self.Sh, name = "strain_mech"), 
                                  dd.DDFunction(self.Sh, name = "stress_mech")])
        self.z_db = dd.DDState([dd.DDFunction(self.Sh, name = "strain_db"), 
                                dd.DDFunction(self.Sh, name = "stress_db")]) 
        self.strain_dim = self.Sh.num_sub_spaces()
        
        self.L = L
        self.grad = grad
        self.dx = self.Sh.dxm
        self.ds = df.Measure('ds', domain = self.Uh.mesh())
        self.bcs = bcs
        self.bcsPF = bcsPF
        
        self.C = self.metric.C_fe
        self.Cinv = self.metric.Cinv_fe
    
        self.solver, self.z = self.create_problem()
        
        self.is_accelerated = is_accelerated
     
    # Typically, you should instanciate self.u, return the solver, and the symbolic update for z    
    def create_problem(self):
        pass         
        # return solver, z
    

    def get_sol(self):
        return {"state" : self.z, # symbolic
                "state_mech" : self.z_mech ,
                "state_db": self.z_db ,
                "u" : self.u }
    
    def solve(self):
        self.solver.solve() 
        
    def accelerated_update(self, z_mech, z_db):

        return [ z_mech[0] + 0.5*self.Cinv*(z_mech[1] - z_db[1]), 
                 z_mech[1] + 0.5*self.C*(z_mech[0] - z_db[0])]
        
    def update_state_mech(self):
        state_update = self.accelerated_update(self.z, self.z_db) if self.is_accelerated else self.z

        for i, z_i in enumerate(self.z_mech):
            z_i.update(state_update[i])
            
    def update_state_db(self, state_db):
        for i, z_i in enumerate(self.z_db):
            z_i.update(state_db[:,i,:].reshape((-1,self.strain_dim)))
            

    def get_state_mech_data(self):
        return np.concatenate(tuple([z_i.data() for i, z_i in enumerate(self.z_mech)]) , axis = 1)

#!/usr/bin/env python
# coding: utf-8

# 0) **Imports**

# In[1]:


import os, sys
from timeit import default_timer as timer
import dolfin as df # Fenics : dolfin + ufl + FIAT + ...
import numpy as np
import matplotlib.pyplot as plt
import fetricks as ft


# 1) **Consititutive behaviour Definition**

# In[12]:


# fetricks is a set of utilitary functions to facilitate our lives
from fetricks.mechanics.elasticity_conversions import youngPoisson2lame
from ddfenics.dd.ddmaterial import DDMaterial 

database_file = 'database_generated.txt'

Nd = 1000 # number of points
noise = 0.01
g_range = np.array([[-0.42, 0.42], [-0.75 , 0.75]]).T

alpha_0 = 1.0
beta = 100

# alpha : Equivalent to sig = lamb*df.div(u)*df.Identity(2) + mu*(df.grad(u) + df.grad(u).T)
def flux(g):
    g2 = np.dot(g,g)
    alpha = alpha_0*(1+beta*g2)
    return -alpha*g

np.random.seed(1)
DD = np.zeros((Nd,2,2))

for i in range(Nd):
    DD[i,0,:] = g_range[0,:] + np.random.rand(2)*(g_range[1,:] - g_range[0,:])
    DD[i,1,:] = flux(DD[i,0,:]) + noise*np.random.randn(2)
    
np.savetxt(database_file, DD.reshape((-1,4)), header = '1.0 \n%d 2 2 2'%Nd, comments = '', fmt='%.8e', )

ddmat = DDMaterial(database_file)  # replaces sigma_law = lambda u : ...

plt.plot(DD[:,0,0], DD[:,1,0], 'o')
plt.xlabel('$g_x$')
plt.ylabel('$q_x$')
plt.grid()


# 2) **Mesh** (Unchanged) 

# In[13]:


Nx =  20 
Ny =  20 
Lx = 1.0
Ly = 1.0
mesh = df.RectangleMesh(df.Point(0.0,0.0) , df.Point(Lx,Ly), Nx, Ny, 'left/right');
df.plot(mesh);


# 3) **Mesh regions** (Unchanged)

# In[14]:


leftBnd = df.CompiledSubDomain('near(x[0], 0.0) && on_boundary')
rightBnd = df.CompiledSubDomain('near(x[0], Lx) && on_boundary', Lx=Lx)

bottomBnd = df.CompiledSubDomain('near(x[1], 0.0) && on_boundary')
topBnd = df.CompiledSubDomain('near(x[1], Ly) && on_boundary', Ly=Ly)

leftFlag = 4
rightFlag = 2
bottomFlag = 1
topFlag = 3

boundary_markers = df.MeshFunction("size_t", mesh, dim=1, value=0)
leftBnd.mark(boundary_markers, leftFlag)
rightBnd.mark(boundary_markers, rightFlag)
bottomBnd.mark(boundary_markers, bottomFlag)
topBnd.mark(boundary_markers, topFlag)


dx = df.Measure('dx', domain=mesh)
ds = df.Measure('ds', domain=mesh, subdomain_data=boundary_markers)


# 4) **Spaces** (Unchanged)

# In[15]:


from ddfenics.dd.ddspace import DDSpace

Uh = df.FunctionSpace(mesh, "CG", 1) # Equivalent to CG
bcBottom = df.DirichletBC(Uh, df.Constant(0.0), boundary_markers, bottomFlag)
bcTop = df.DirichletBC(Uh, df.Constant(0.0), boundary_markers, topFlag)
bcs = [bcBottom, bcTop]

# Space for stresses and strains
Sh0 = DDSpace(Uh, 2, 'DG') 

spaces = [Uh, Sh0]


# 5) **Variational Formulation**: <br>
# 
# - Strong format: 
# $$
# \begin{cases}
# div \mathbb{q} = f  \text{in} \, \Omega \\
# u = 0 \quad \text{on} \, \Gamma_1 \cup \Gamma_3 \\
# \mathbf{g} = -\nabla u \quad \text{in} \, \Omega \\
# \mathbf{q} \cdot n  = \bar{q}_{2,4} \quad \text{on} \, \Gamma_2 \cup \Gamma_4 \\
# \end{cases}
# $$ 
# - DD equilibrium subproblem: Given $(\varepsilon^*, \sigma^*) \in Z_h$, solve for $(u,\eta) \in U_h$  
# $$
# \begin{cases}
# (\mathbb{C} \nabla^s u , \nabla^s v ) = -(\mathbb{C} \mathbf{g}^* , \nabla v ) \quad \forall v \in U_h, \\
# (\mathbb{C} \nabla^s \eta , \nabla^s \xi ) = \Pi_{ext}(\xi) - (\mathbf{q}^* , \nabla \xi ) \quad \forall \xi \in U_h \\
# \end{cases}
# $$
# - Updates:
# $$
# \begin{cases}
# \mathbf{g} = -\nabla u \\
# \mathbf{q} = \mathbf{q}^* + \mathbb{C} \nabla \eta
# \end{cases}
# $$
# - DD ''bilinear'' form : $(\bullet , \nabla v)$ or sometimes  $(\mathbb{C} \nabla \bullet, \nabla v)$ 

# In[21]:


# Changed
from ddfenics.dd.ddmetric import DDMetric
from ddfenics.dd.ddbilinear import DDBilinear

# Unchanged
uh = df.TrialFunction(Uh)
vh = df.TestFunction(Uh)


flux_left = df.Constant(10.0)
flux_right = df.Constant(1.0)
source = df.Constant(10.0)

P_ext = source*vh*dx + flux_left*vh*ds(leftFlag) + flux_right*vh*ds(rightFlag)

# changed 
C = alpha_0*np.eye(2)
dddist = DDMetric(C = C, V = Sh0, dx = dx)


# 6) **Statement and Solving the problem** <br> 
# - DDProblem : States DD equilibrium subproblem and updates.
# - DDSolver : Implements the alternate minimization using SKlearn NearestNeighbors('ball_tree', ...) searchs for the projection onto data.
# - Stopping criteria: $\|d_k - d_{k-1}\|/energy$

# In[22]:


from ddfenics.dd.ddfunction import DDFunction
from ddfenics.dd.ddproblem_poisson import DDProblemPoisson as DDProblem # Generic implementation
from ddfenics.dd.ddsolver import DDSolver

# replaces df.LinearVariationalProblem(a, b, uh, bcs = [bcL])
problem = DDProblem(spaces, df.grad, L = P_ext, bcs = bcs, metric = dddist) 
sol = problem.get_sol()

start = timer()

#replaces df.LinearVariationalSolver(problem)
solver = DDSolver(problem, ddmat, opInit = 'zero', seed = 1)
tol_ddcm = 1e-7
solver.solve(tol = tol_ddcm, maxit = 100);

end = timer()

uh = sol["u"]
normL2 = df.assemble(df.inner(uh,uh)*dx)
norm_energy = df.assemble(df.inner(sol['state_mech'][0],sol['state_mech'][1])*dx)

print("Time spent: ", end - start)
print("Norm L2: ", normL2)
print("Norm energy: ", norm_energy)


# 7) **Plotting**

# a) *Minimisation*

# In[19]:


hist = solver.hist

fig = plt.figure(2)
plt.title('Minimisation')
plt.plot(hist['relative_energy'], 'o-')
plt.xlabel('iterations')
plt.ylabel('energy')
plt.legend(loc = 'best')
plt.yscale('log')
plt.grid()

fig = plt.figure(3)
plt.title('Relative distance (wrt k-th iteration)')
plt.plot(hist['relative_distance'], 'o-', label = "relative_distance")
plt.plot([0,len(hist['relative_energy'])],[tol_ddcm,tol_ddcm], label = "threshold")
plt.yscale('log')
plt.xlabel('iterations')
plt.ylabel('rel. distance')
plt.legend(loc = 'best')
plt.grid()


#  

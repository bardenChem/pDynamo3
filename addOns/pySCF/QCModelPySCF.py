"""The PySCF QC model."""

import glob, os

try:
    import pyscf
    _PYSCFFound = True
except:
    _PYSCFFound = False
from pyscf import qmmm
from pCore             import NotInstalledError
from pMolecule.QCModel import QCModel           , \
                              QCModelError
from pScientific       import Units

# Initialize GPU variables with safe defaults
GPU_AVAILABLE = False
HAS_CUDA = False
GPU4PYSCF_AVAILABLE = False
RKS_GPU = None
UKS_GPU = None

# Attempt GPU detection safely
try:
    import cupy as cp
    try:
        cp.cuda.runtime.getDeviceCount()
        HAS_CUDA = True
    except Exception:
        pass  # CUDA runtime/driver issue
    
    if HAS_CUDA:
        try:
            import gpu4pyscf
            from gpu4pyscf.dft import RKS, UKS
            GPU4PYSCF_AVAILABLE = True
            GPU_AVAILABLE = True
            RKS_GPU = RKS
            UKS_GPU = UKS
            print("Info: GPU acceleration available")
        except ImportError:
            print("Info: gpu4pyscf not installed, GPU disabled")
    else:
        print("Info: CUDA not available, using CPU only")
        
except ImportError:
    print("Info: CuPy not installed, using CPU only")


#===================================================================================================================================
# . Parameters.
#===================================================================================================================================
_DefaultFunctional = "blyp"

#===================================================================================================================================
# . Class.
#===================================================================================================================================
class QCModelPySCF ( QCModel ):
    """The PySCF QC model class."""

    _attributable = dict ( QCModel._attributable )
    _classLabel   = "PySCF QC Model"
    _summarizable = dict ( QCModel._summarizable )
    _attributable.update ( { "deleteJobFiles" : True    ,
                             "functional"     : "blyp"  ,
                             "method"         : "RHF"   , 
                             "mf"             : None    , 
                             "mf_kwargs"      : dict    ,
                             "mole"           : None    ,
                             "mole_kwargs"    : dict    , 
                             "orbitalBasis"   : "3-21G" ,
                             "pyscf"          : None    ,
                             "pySCFscratch"   : None    } )
    _summarizable.update ( { "functional"     : "Functional"    ,
                             "method"         : "Method"        ,
                             "orbitalBasis"   : "Orbital Basis" } )


    def __del__ ( self ):
        """Deallocation."""
        self.DeleteJobFiles ( )

    def _CheckOptions ( self ):
        """Check options."""
        super ( QCModelPySCF, self )._CheckOptions ( )
        # . pySCF.
        if _PYSCFFound: self.pyscf = pyscf
        else: raise NotInstalledError ( "pySCF not installed." )
        # . pySCFscratch.
        scratch = os.getenv ( 'PYSCF_TMPDIR' )
        if scratch is None:
            scratch                    = os.getenv ( "PDYNAMO3_SCRATCH" )
            os.environ['PYSCF_TMPDIR'] = str ( scratch )
        self.pySCFscratch = scratch
        # . Functional.
        if ( 'KS' in self.method.upper ( ) ) and ( self.functional is None ):
            self.functional = _DefaultFunctional
        self.molden_name=self.mole_kwargs["molden_name"]
        del self.mole_kwargs["molden_name"]

    def CreateMole ( self, target, doQCMM ):
        """Create PySCF mole and mean-field objects"""
        state        = getattr ( target, self.__class__._stateName )
        n            = len ( state.atomicNumbers )
        coordinates3 = target.scratch.qcCoordinates3AU
        mole         = self.pyscf.gto.Mole()
        mole.atom    = [[state.atomicNumbers[i], (coordinates3[i][0], coordinates3[i][1], coordinates3[i][2])] for i in range(n)]
        mole.basis   = self.orbitalBasis        
        mole.charge  = target.electronicState.charge
        mole.spin    = target.electronicState.multiplicity - 1 # 2S
        mole.unit    = 'Bohr'
        mole.verbose = 4
        mole.__dict__.update(self.mole_kwargs)
        state.mole = mole.build()
        state.mf   = state.mole.apply ( self.method, **self.mf_kwargs )
        if doQCMM:
            charges       = []
            chargesB      = getattr ( target.qcmmState, "bpCharges", None )
            chargesM      = target.mmState.charges
            coords        = []
            coordinates3B = target.scratch.Get ( "bpCoordinates3", None                ) 
            coordinates3M = target.scratch.Get ( "coordinates3NB", target.coordinates3 )
            mmAtoms       = target.mmState.pureMMAtoms
            qScale        = 1.0 / target.qcmmElectrostatic.dielectric
            nM            = len ( mmAtoms )
            if chargesB is None: nB = 0
            else:                nB = len ( chargesB )
            for i in mmAtoms:
               charges.append(qScale * chargesM[i])
               coords.append ([ coordinates3M[i,0], coordinates3M[i,1], coordinates3M[i,2] ])
            for i in range ( nB ):
               charges.append(qScale * chargesB[i])
               coords.append ([ coordinates3B[i,0], coordinates3B[i,1], coordinates3B[i,2] ])
            # . Coordinates for MM centers stored in Angstroms.
            state.mf = self.pyscf.qmmm.add_mm_charges(state.mf, coords, charges, unit='Angstrom')

    def DeleteJobFiles ( self ):
        """Delete job files."""
        if self.deleteJobFiles:
            try:
                jobFiles = glob.glob ( os.path.join ( self.pySCFscratch, "tmp????????" ) )
                for jobFile in jobFiles: os.remove ( jobFile )
            except:
                pass

    def Energy ( self, target ):
        """Calculate the quantum chemical energy and gradient."""
        state           = getattr ( target, self.__class__._stateName )
        xc              = None
        if 'KS' in self.method.upper(): xc = self.functional
        doGradients     = target.scratch.doGradients
        doQCMM          = ( len ( target.atoms ) > len ( state.qcAtoms ) )
        

        gpu_mode = False
        if GPU_AVAILABLE and xc is not None:
            gpu_mode = True
            print("Info: Running PySCF on GPU")

        try:
            self.CreateMole(target, doQCMM)

            if gpu_mode:
                if "restricted" in str(self.method).lower():
                    state.mf = RKS_GPU(state.mole, xc=xc)
                    print("Info: Running PySCF DFT on GPU! Created with RKS with functional:", xc)
                else:
                    state.mf = UKS_GPU(state.mole, xc=xc)
                    print("Info: Running PySCF DFT on GPU! Created with UKS with functional:", xc)
            elif xc is not None:
            # CPU DFT
                from pyscf.dft import RKS, UKS
                if "restricted" in str(self.method).lower():
                    state.mf = RKS(state.mole, xc=xc)
                    print("Info: Running PySCF DFT on CPU! Created with RKS with functional:", xc)
                else:
                    state.mf = UKS(state.mole, xc=xc)
                    print("Info: Running PySCF DFT on CPU! Created with UKS with functional:", xc)
            else:
                # CPU Hartree-Fock (non-DFT)
                from pyscf.scf import RHF, UHF
                if "restricted" in str(self.method).lower():
                    state.mf = RHF(state.mole)
                    print("Info: Running PySCF Hartree-Fock on CPU! Created with RHF")
                else:
                    state.mf = UHF(state.mole)
                    print("Info: Running PySCF Hartree-Fock on CPU! Created with UHF")  

            print(f"Current energy convergence tolerance: {state.mf.conv_tol}") 
            print(f"Current gradient convergence tolerance: {state.mf.conv_tol_grad}")   
            state.mf.conv_tol = 1e-6
            state.mf.conv_tol_grad = 0.001
            state.mf.max_cycle = 100
            state.mf.verbose = 4 
            state.mf.run(xc=xc)

               
            from pyscf.tools import molden
            if gpu_mode:
                mf_cpu = state.mf.to_cpu()  # Transfer data back to CPU for molden
                try: molden.dump_scf(mf_cpu, self.molden_name)
                except: raise QCModelError ("Error in dumping molden file.")
            else:
                try: molden.dump_scf(state.mf, self.molden_name)
                except: raise QCModelError ("Error in dumping molden file.")            
        
            if not state.mf.converged: raise QCModelError ( "SCF energy calculation did not converge." )
        
            energy_hartree = 0.0
            if gpu_mode:
                energy_hartree = float(state.mf.energy_tot())  # Get energy from GPU calculation
            else: 
                energy_hartree = state.mf.energy_tot()  # Get energy from CPU calculation

            target.scratch.energyTerms["PySCF QC"] = ( energy_hartree * Units.Energy_Hartrees_To_Kilojoules_Per_Mole )
            ga_cpu = None
            if doGradients:
                try: 
                    if gpu_mode:
                        g = state.mf.nuc_grad_method()  # Ensure data is on CPU for gradient calculation
                        ga = g.kernel()
                        ga_cpu = ga.get() if hasattr(ga, 'get') else ga  # Handle case where g.kernel() returns CPU array
                    else:
                        g = state.mf.nuc_grad_method()
                        ga_cpu = g.kernel()
            
                    # . QC gradients
                    for i in range ( len ( state.atomicNumbers ) ):
                        for j in range ( 3 ):
                            target.scratch.qcGradients3AU[i,j] = ga_cpu[i,j]

                except:
                    raise QCModelError ( "Error calculating PySCF gradient." ) 
        
        except:
            raise QCModelError ( "Error calculating PySCF energy." )
        
#===================================================================================================================================
# . Testing.
#===================================================================================================================================
if __name__ == "__main__" :
    pass


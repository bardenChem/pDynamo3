#!/bin/csh

# . Cshell environment variables and paths to be added to a user's ".cshrc" file.
# . PDYNAMO3_ORCACOMMAND, PDYNAMO3_SCRATCH and PYTHONPATH will likely need modifying.

# . The root of the program.
setenv PDYNAMO3_HOME             /home/igorchem/programs/pDynamo3

# . Additional paths.
setenv PDYNAMO3_ORCACOMMAND      $HOME/programs/orca_local/orca  
setenv PDYNAMO3_PARAMETERS       $PDYNAMO3_HOME/parameters
setenv PDYNAMO3_PYTHONCOMMAND    python3
setenv PDYNAMO3_SCRATCH          $PDYNAMO3_HOME/scratch
setenv PDYNAMO3_STYLE            $PDYNAMO3_PARAMETERS/ccsStyleSheets/defaultStyle.css

# . The python path.
setenv PYTHONPATH ,:$PDYNAMO3_HOME

# Introduction

Publications related to the [dVRK](https://github.com/jhu-dvrk/sawIntuitiveResearchKit/wiki).  Initial database created for article *Accelerating Surgical Robotics Research: Reviewing 10 Years of Research with the dVRK*  by *Claudia D'Ettorre, Andrea Mariani, Agostino Stilli, Ferdinando Rodriguez y Baena, Pietro Valdastri, Anton Deguet, Peter Kazanzides, Russell H. Taylor, Gregory S. Fischer, Simon P. DiMaio, Arianna Menciassi, Danail Stoyanov* ([arXiv](https://arxiv.org/abs/2104.09869)).

We hope dVRK users will update this database when they publish new work.  To update the database, please fork this repository, edit the `publications.bib` file and issue a pull request.

There is also a (limited) web interface for the database: https://dvrk.lcsr.jhu.edu/community-publications/

# Custom fields 

Please try to add these fields to new publications and use the existing codes as much as possible.  When multiple values are required, separate them with a "` and `".  For more details regarding the code definition, please read the article mentioned above.

## Research field 

The field is `research_field`.  Possible values:
* `AU`:
* ...

## Data type

The field is `data_type`.  For example: `data_type={RI and KD and SD and ED}`.  Possible values:
* `RI`: Raw Images
* `KD`: Kinematic Data
* `SD`: System Data
* `ED`: External Data

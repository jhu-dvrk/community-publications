# Introduction

Publications related to the [dVRK](https://github.com/jhu-dvrk/sawIntuitiveResearchKit/wiki).  Initial database created for article *Accelerating Surgical Robotics Research: Reviewing 10 Years of Research with the dVRK*  by *Claudia D'Ettorre, Andrea Mariani, Agostino Stilli, Ferdinando Rodriguez y Baena, Pietro Valdastri, Anton Deguet, Peter Kazanzides, Russell H. Taylor, Gregory S. Fischer, Simon P. DiMaio, Arianna Menciassi, Danail Stoyanov* ([arXiv](https://arxiv.org/abs/2104.09869)).

We hope dVRK users will update this database when they publish new work.  To update the database, please fork this repository, edit the `publications.bib` file and issue a pull request.

There is also a (limited) web interface for the database: https://dvrk.lcsr.jhu.edu/community-publications/

# Custom fields 

Please try to add these fields to new publications and use the existing codes as much as possible.  When multiple values are required, separate them with a "` and `".  For more details regarding the code definition, please read the article mentioned above.

## Research field 

The field is `research_field`.  Possible values:
* `AU`: **Automation**

This field refers to all the works automating any aspect of robotic surgery in order to improve the surgical workflow or to optimize the performance in a certain task. Specifically, here we find research efforts introducing autonomy in terms of: `general control` (i.e., works focused on developing new high-level control architectures without specializing on task-oriented applications); `instrument control` (i.e., all the contributions towards the automation of specific surgical subtasks, like suturing, pick and place, or tissue manipulation, and so on); `camera control` (including the literature that investigated how to relieve the surgeon from switching between the instrument and the camera control by introducing autonomous navigation of the endoscopic camera).

* `TR`: **Training, skill assessment and gesture recognition**

In this field, we grouped all the publications where new `training platforms and protocols` were designed and evaluated, as well as the research efforts towards learning enhancement by multi-sensory `training augmentation`. Here, a special mention goes to haptic guidance or virtual fixtures applied during training. As a fundamental component of training, `skill assessment` has received attention especially towards objective and automated technical skill evaluation. Finally, `workflow analysis` by surgical gesture identification and segmentation was widely investigated with particular interest in combining image analysis and robot kinematics. 

* `HW`: **Hardware implementation and integration**

This quite heterogeneous field encompasses all the work that have contributed to develop the dVRK system, as well as further modifications of its software and hardware to make surgery more affordable and capable to interface with other surgical equipment.
First of all, here we find all the papers published during the `development of the dVRK platform` itself. Then, we have works related to `haptics`, trying to integrate the surgical tools with force sensing, or using virtual fixtures as an intra operative guidance tool, as well as taking advantage of augmented reality to provide the surgeon with visual feedback about forces (the so called pseudo-haptics). Some works focused on the design and integration of `new surgical tools` (surgical instruments and sensing tools), while others reported the development of `new control interfaces`, like using head mounted displays to control the camera or improving the ergonomics and the portability of the master console.
To `optimize the surgical workflow`, some research efforts tried to enhance the surgeon’s awareness and perception or to improve the teleoperation capabilities of the da Vinci. Finally, few additional works investigated the use of the `dVRK beyond its current surgical intent`, both in other surgical specialties (e.g., for retinal surgery) or for non-surgical applications, like using the master controllers to drive vehicles in simulation.

* `SS`: **System simulation and modelling**

This field contains only studies that focused on the integration of the dVRK into simulation environments without any direct application inside the publication itself. Here we have works focused on optimizing simulation to obtain `realistic robot interactions with rigid and soft objects`, as well as works related to robot `parametrization`, that means the identification of the kinematics and dynamics properties of the robotic arms for external forces estimation and other applications.

* `IM`: **Imaging and vision**

This field encompasses all the publications related to the processing of the images acquired by the endoscopic camera. `Camera and hand-eye calibration` includes publications investigating approaches to register the coordinate systems of the endoscope and the surgical tools  as well as determining the camera intrinsic parameters. A wide range of papers reported algorithms aimed at `detecting, segmenting, and tracking` important elements in the surgical scene, such as surgical instruments, tissues, and so on. Image processing was also finalized to `spatial mapping and understanding`, like to estimate the depth of the workspace, or to automatically remove smoke from the surgeon field of view. Finally, the dVRK research tried to keep up with `novel imaging capabilities` like interfacing standard imaging with the one from miniaturized ultrasound probes or photoacoustic imaging, or implementing other kinds of `image augmentation` to assist the surgeon throughout the surgical procedure.

* `RE`: **Reviews**

Review papers that cite the dVRK platform. 


## Data type

The field is `data_type`.  For example: `data_type={RI and KD and SD and ED}`.  Possible values:
* `RI`: Raw Images, the left and right video stream from the da Vinci stereo endoscope or any other cameras
* `KD`: Kinematic Data, information associated to the kinematics of the dVRK (including ECM, MTMs, PSMs and SUJ) 
* `DD`: Dynamic Data, information associated to the dynamics of the dVRK (including ECM, MTMs, PSMs) 
* `SD`: System Data, the data associated to the robot teleoperation states, as signals coming from foot pedals, head sensor for operator presence detection, etc.
* `ED`: External Data, all the data associated with additional technologies that were used along with the dVRK, such as eye trackers, force sensors, different imaging technologies, etc. 

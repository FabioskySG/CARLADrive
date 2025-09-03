# CARLADrive

* Modify PATH_TO_DATASET in Makefile
* Modify ROUTES in pdm_lite/start_expert_local_base.sh (change .xml for the desired routes). The default set is located in pdm_lite/leaderboard/data/
* Major modifications have been made to pdm_lite/team_code/data_agent.py in order to gather the required data for the dataset.
* New sensor suite has been created in pdm_lite/team_code/config_nusc.py to match nuScenes' sensor suite as closely as possible. 

* Check pdm_lite README for more information about installing and running CARLA in case of needing to generate new or different data.

* Once data is created, it is neccesary to run format_dataset.py pointing to the data folder to generate the labels and pointclouds from the data gathered by the PDM-Lite agent.


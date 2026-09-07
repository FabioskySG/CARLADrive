import os
import json
import gzip
import random
from tqdm import tqdm

import numpy as np
import laspy

from pdm_lite.team_code.config_nusc import GlobalConfigNusc

def create_transformation_matrix(rotation_matrix, translation_vector):
    """
    Creates a homogeneous transformation matrix 4x4 from
    a rotation matrix 3x3 and a translation vector 3x1
    """
    transform = np.eye(4)
    transform[:3, :3] = rotation_matrix
    transform[:3, 3] = translation_vector
    return transform

def check_collisions(route_folder: str):
    RESULTS_PATH = os.path.join(route_folder, "results.json.gz")
    MEASUREMENTS_FOLDER = os.path.join(route_folder, "measurements")

    with gzip.open(RESULTS_PATH, 'rt', encoding='utf-8') as f:
        results = json.load(f)

    collisions = {
        "agent_collided": [],
        "id_collided": [],
        "x_collided": [],
        "y_collided": [],
    }

    for key in results['infractions'].keys():
        if 'collision' in key:
            collision = results['infractions'][key]
            if len(collision) > 0:
                for coll in collision:
                    # get id of collided element and position
                    coll = coll.split(" ")
                    for element in coll:
                        if "type=" in element:
                            element = element.split("=")[1]
                            collisions["agent_collided"].append(element)
                        if "id=" in element:
                            element = element.split("=")[1]
                            collisions["id_collided"].append(element)
                        if "x=" in element:
                            element = element.split("=")[1]
                            element = element[:-1]
                            collisions["x_collided"].append(element)
                        if "y=" in element:
                            element = element.split("=")[1]
                            element = element[:-1]
                            collisions["y_collided"].append(element)
                        
    files = os.listdir(MEASUREMENTS_FOLDER) # files are in format: 0000.json.gz
    files = sorted(files)

    pos_coll = [(float(x), float(y)) for x, y in zip(collisions["x_collided"], collisions["y_collided"])]

    thres = 5
    invalid_files = []

    for file in files: 
        # Check if file is json.gz
        if file.endswith(".json.gz"):
            with gzip.open(os.path.join(MEASUREMENTS_FOLDER, file), 'rt', encoding='utf-8') as f:
                data = json.load(f)
                pos_global = data['pos_global']            
                for coll in pos_coll:
                    if -thres < pos_global[0] - coll[0] < thres and -thres < pos_global[1] - coll[1] < thres:
                        invalid_files.append(file.split(".json.gz")[0])

    # Save invalid files in a text file.
    with open(os.path.join(route_folder, "invalid_files.txt"), "w") as f:
        for file in invalid_files:
            f.write(file + "\n")

    return invalid_files

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Format dataset")
    # parser.add_argument("--split", "-s", type=str, default="CARLADrive_routes_mini", help="Split Type")
    parser.add_argument("--path", "-p", type=str, default="/home/carladrive/Datasets/CARLADrive/", help="Dataset Path")
    args = parser.parse_args()

    config = GlobalConfigNusc()

    DATASET_PATH = args.path

    # DATASET_PATH = "/home/carladrive/Datasets/CARLADrive/" + args.split

    # List all routes. Two supported layouts:
    #  1. Standard: DATASET_PATH contains 'routes_training'/'routes_validation' subfolders,
    #     each holding route_* folders (the layout produced by two separate data-generation
    #     runs, one per routes file).
    #  2. Flat: DATASET_PATH directly contains route_* folders, with no training/validation
    #     split (e.g. a quick one-off run against a single custom routes file).
    train_route_names = []
    val_route_names = []
    subdirs = sorted(d for d in os.listdir(DATASET_PATH) if os.path.isdir(os.path.join(DATASET_PATH, d)))

    train_split_dir, val_split_dir = None, None
    for route in subdirs:
        if "training" in route:
            train_split_dir = route
        elif "validation" in route:
            val_split_dir = route

    if train_split_dir or val_split_dir:
        if train_split_dir:
            for tr_route in sorted(os.listdir(os.path.join(DATASET_PATH, train_split_dir))):
                if "route" not in tr_route:
                    continue
                train_route_names.append(os.path.join(DATASET_PATH, train_split_dir, tr_route))
        if val_split_dir:
            for val_route in sorted(os.listdir(os.path.join(DATASET_PATH, val_split_dir))):
                if "route" not in val_route:
                    continue
                val_route_names.append(os.path.join(DATASET_PATH, val_split_dir, val_route))
    else:
        flat_routes = [d for d in subdirs if "route" in d]
        if not flat_routes:
            raise SystemExit(
                f"No routes found under {DATASET_PATH}. Expected either 'routes_training'/"
                f"'routes_validation' subfolders, or 'route_*' folders directly inside it."
            )
        print(f"No routes_training/routes_validation split found under {DATASET_PATH}; "
              f"treating all {len(flat_routes)} route folder(s) found there as a flat set.")
        train_route_names = [os.path.join(DATASET_PATH, r) for r in flat_routes]

    # This dict will count the global instances of each class.
    class_dict = {
                "car": 0,
                "bicycle": 0,
                "walker": 0,
                "traffic_light": 0,
                "stop_sign": 0,
                "static_trafficwarning": 0,
            }

    route_names = train_route_names + val_route_names

    for route in route_names:
        DATAROOT = route
        BOXES_PATH = os.path.join(DATAROOT, "boxes")
        MEASUREMENTS_PATH = os.path.join(DATAROOT, "measurements")
        print("DATAROOT: ", DATAROOT)

        # Read number of files in the folders.
        n_files = len([name for name in os.listdir(BOXES_PATH) if os.path.isfile(os.path.join(BOXES_PATH, name))])
        print("Number of files in boxes folder: ", n_files)

        for ITEM in tqdm(range(n_files)):
            ITEM = str(ITEM).zfill(4)

            # Load measurements.
            with gzip.open(os.path.join(MEASUREMENTS_PATH, ITEM + ".json.gz"), "rb") as f:
                measurements = json.load(f)

            # Load boxes.
            with gzip.open(os.path.join(BOXES_PATH, ITEM + ".json.gz"), "rb") as f:
                boxes = json.load(f)

            P_CAM_FRONT = config.camera_front_K
            P_CAM_FRONT_LEFT = config.camera_front_left_K
            P_CAM_FRONT_RIGHT = config.camera_front_right_K
            P_CAM_BACK = config.camera_back_K
            P_CAM_BACK_LEFT = config.camera_back_left_K
            P_CAM_BACK_RIGHT = config.camera_back_right_K

            # ------------------------------- Transformation matrixes -------------------------------------
            ego2lidar = config.ego2lidar
            ego2cam_front = config.ego2camera_front
            ego2cam_front_left = config.ego2camera_front_left
            ego2cam_front_right = config.ego2camera_front_right
            ego2cam_back = config.ego2camera_back
            ego2cam_back_left = config.ego2camera_back_left
            ego2cam_back_right = config.ego2camera_back_right
            ego2radar_front = config.ego2radar_front
            ego2radar_front_left = config.ego2radar_front_left
            ego2radar_front_right = config.ego2radar_front_right
            ego2radar_back_left = config.ego2radar_back_left
            ego2radar_back_right = config.ego2radar_back_right

            lidar2ego = np.linalg.inv(ego2lidar)
            
            lidar2cam_front = ego2cam_front @ lidar2ego
            lidar2cam_front_left = ego2cam_front_left @ lidar2ego
            lidar2cam_front_right = ego2cam_front_right @ lidar2ego
            lidar2cam_back = ego2cam_back @ lidar2ego
            lidar2cam_back_left = ego2cam_back_left @ lidar2ego
            lidar2cam_back_right = ego2cam_back_right @ lidar2ego
            lidar2radar_front = ego2radar_front @ lidar2ego
            lidar2radar_front_left = ego2radar_front_left @ lidar2ego
            lidar2radar_front_right = ego2radar_front_right @ lidar2ego
            lidar2radar_back_left = ego2radar_back_left @ lidar2ego
            lidar2radar_back_right = ego2radar_back_right @ lidar2ego
            # ---------------------------------------------------------------------------------------------

            ego_matrix = np.array(measurements["ego_matrix"])

            # Create the directory if it does not exist.
            os.makedirs(os.path.join(DATAROOT, "calib"), exist_ok=True)

            with open(os.path.join(DATAROOT, "calib", ITEM + ".txt"), "w") as f:
                f.write("CAM_FRONT_K: " + " ".join(map(str, P_CAM_FRONT.flatten())) + "\n")
                f.write("CAM_FRONT_LEFT_K: " + " ".join(map(str, P_CAM_FRONT_LEFT.flatten())) + "\n")
                f.write("CAM_FRONT_RIGHT_K: " + " ".join(map(str, P_CAM_FRONT_RIGHT.flatten())) + "\n")
                f.write("CAM_BACK_K: " + " ".join(map(str, P_CAM_BACK.flatten())) + "\n")
                f.write("CAM_BACK_LEFT_K: " + " ".join(map(str, P_CAM_BACK_LEFT.flatten())) + "\n")
                f.write("CAM_BACK_RIGHT_K: " + " ".join(map(str, P_CAM_BACK_RIGHT.flatten())) + "\n")
                f.write("LIDAR2CAM_FRONT: " + " ".join(map(str, lidar2cam_front.flatten())) + "\n")
                f.write("LIDAR2CAM_FRONT_LEFT: " + " ".join(map(str, lidar2cam_front_left.flatten())) + "\n")
                f.write("LIDAR2CAM_FRONT_RIGHT: " + " ".join(map(str, lidar2cam_front_right.flatten())) + "\n")
                f.write("LIDAR2CAM_BACK: " + " ".join(map(str, lidar2cam_back.flatten())) + "\n")
                f.write("LIDAR2CAM_BACK_LEFT: " + " ".join(map(str, lidar2cam_back_left.flatten())) + "\n")
                f.write("LIDAR2CAM_BACK_RIGHT: " + " ".join(map(str, lidar2cam_back_right.flatten())) + "\n")
                f.write("LIDAR2RADAR_FRONT: " + " ".join(map(str, lidar2radar_front.flatten())) + "\n")
                f.write("LIDAR2RADAR_FRONT_LEFT: " + " ".join(map(str, lidar2radar_front_left.flatten())) + "\n")
                f.write("LIDAR2RADAR_FRONT_RIGHT: " + " ".join(map(str, lidar2radar_front_right.flatten())) + "\n")
                f.write("LIDAR2RADAR_BACK_LEFT: " + " ".join(map(str, lidar2radar_back_left.flatten())) + "\n")
                f.write("LIDAR2RADAR_BACK_RIGHT: " + " ".join(map(str, lidar2radar_back_right.flatten())) + "\n")
                f.write("LIDAR2EGO: " + " ".join(map(str, lidar2ego.flatten())) + "\n")
                f.write("EGO_MATRIX: " + " ".join(map(str, ego_matrix.flatten())) + "\n")

            items = []

            # Labels format: [<object_type> <width> <height> <length> <x> <y> <z> <rotation_y> <num_points> <speed_x> <speed_y>]
            # x, y, z are the coordinates of the object in ego's reference frame. Z is from the ground. 
            # width, height, length are the dimensions of the object
            # rotation_y is the yaw rotation of the object
            # num_points is the number of lidar hits in the object

            for i, box in enumerate(boxes):
                if box["class"] == "car" or box["class"] == "static_car": # coche
                    # CARLA base types are car, truck, van, bus, bicycle.
                    # Car, truck, van and bus are considered as "car".
                    if ("base_type" in box) and box["base_type"] == "bicycle":
                        base_type = "bicycle"
                    else:
                        base_type = "car"
                    speed = box.get("speed", 0.0)
                    speed_x = speed * np.cos(np.deg2rad(float(box["yaw"])))
                    speed_y = speed * np.sin(np.deg2rad(float(box["yaw"])))
                    items.append([base_type, 
                            np.array(box["extent"][1])*2,   # w
                            np.array(box["extent"][2])*2,   # h
                            np.array(box["extent"][0])*2,   # l
                            box["position"][0],             # x
                            -box["position"][1],            # -y, due to CARLA coordinates.
                            box["position"][2],             # z
                            -float(box["yaw"]),             # -yaw, due to CARLA coordinates.
                            box["num_points"],              # num_points
                            speed_x,                        # speed_x
                            speed_y])                       # speed_y
                    class_dict[base_type] += 1
                elif box["class"] == "walker":
                    speed = box.get("speed", 0.0)
                    speed_x = speed * np.cos(np.deg2rad(float(box["yaw"])))
                    speed_y = speed * np.sin(np.deg2rad(float(box["yaw"])))
                    items.append(["walker", 
                                0.5,                          # Fixed shape.
                                np.array(box["extent"][2])*2, # Depends on child, adult...
                                0.5,                          # Fixed shape.
                                box["position"][0],           # x
                                -box["position"][1],          # -y, due to CARLA coordinates.
                                0,                            # z, assume ground level.
                                -float(box["yaw"]),             
                                box["num_points"],
                                speed_x,
                                speed_y])
                    class_dict["walker"] += 1
                elif box["class"] == "traffic_light_vqa":
                        if box["state"] == "Red":
                            state = 0
                        elif box["state"] == "Yellow":
                            state = 1
                        elif box["state"] == "Green":
                            state = 2
                        else:
                            state = box["state"]
                        # Traffic lights are not correctly labeled in CARLA, since they only offer the
                        # position of the TL base. We need some modifications and offsets.
                        x = box["position"][0]
                        y = box["position"][1]
                        z = 5.5 # in meters
                        yaw = float(box["yaw"]) + np.pi
                        x += 6 * np.cos(yaw)
                        y += 6 * np.sin(yaw)
                        items.append(["traffic_light", 
                                    0.4,   
                                    0.9, 
                                    0.4, 
                                    x,             
                                    -y, 
                                    z, 
                                    -float(box["yaw"]),
                                    box["num_points"],
                                    state])
                        class_dict["traffic_light"] += 1
                elif box["class"] == "stop_sign_vqa":
                        if not box["affects_ego"]:  # Only consider stop signs that FACE TOWARDS the ego vehicle.
                            continue
                        items.append(["stop_sign", 
                                    0.25,   
                                    0.9, 
                                    0.9, 
                                    box["position"][0],             
                                    -box["position"][1], 
                                    1.5, 
                                    -float(box["yaw"]), 
                                    box["num_points"]])
                        class_dict["stop_sign"] += 1
                elif box["class"] == "static_trafficwarning":
                        items.append(["static_trafficwarning", 
                                    3.0,
                                    np.array(box["extent"][2])*2, # h
                                    2.5,
                                    box["position"][0],             
                                    -box["position"][1], 
                                    box["position"][2], 
                                    -float(box["yaw"]), 
                                    box["num_points"]])
                        class_dict["static_trafficwarning"] += 1
                elif box["class"] == "weather":
                    items.append(["weather",
                                box["cloudiness"],
                                box["dust_storm"],
                                box["fog_density"],
                                box["fog_distance"],
                                box["fog_falloff"],
                                box["mie_scattering_scale"],
                                box["precipitation"],
                                box["precipitation_deposits"],
                                box["rayleigh_scattering_scale"],
                                box["scattering_intensity"],
                                box["sun_altitude_angle"],
                                box["sun_azimuth_angle"],
                                box["wetness"],
                                box["wind_intensity"]])
                else:
                    pass

            # create the directory if it does not exist
            os.makedirs(os.path.join(DATAROOT, "labels"), exist_ok=True)

            with open(os.path.join(DATAROOT, "labels", ITEM + ".txt"), "w") as f:
                for item in items:
                    f.write(" ".join(map(str, item)) + "\n")

            # Open pointcloud in LAZ format.
            LIDAR_PATH = os.path.join(DATAROOT, "lidar", ITEM + ".laz")

            with laspy.open(LIDAR_PATH) as f:
                points = f.read()

            x = points['X']/1000 + f.header.offset[0]
            y = points['Y']/1000 + f.header.offset[1]
            z = points['Z']/1000 + f.header.offset[2]
            i = points['intensity']

            # Save in points folder as .bin
            os.makedirs(os.path.join(DATAROOT, "points"), exist_ok=True)

            with open(os.path.join(DATAROOT, "points", ITEM + ".bin"), "wb") as f:
                np.array([x, y, z, i]).T.astype(np.float32).tofile(f)

            # Combine radar pointclouds to create only one.
            RADAR_PATHS = [
                os.path.join(DATAROOT, "RADAR_FRONT", ITEM + ".bin"),
                os.path.join(DATAROOT, "RADAR_FRONT_LEFT", ITEM + ".bin"),
                os.path.join(DATAROOT, "RADAR_FRONT_RIGHT", ITEM + ".bin"),
                os.path.join(DATAROOT, "RADAR_BACK_LEFT", ITEM + ".bin"),
                os.path.join(DATAROOT, "RADAR_BACK_RIGHT", ITEM + ".bin"),
            ]

            RADARS = [
                "RADAR_FRONT",
                "RADAR_FRONT_LEFT",
                "RADAR_FRONT_RIGHT",
                "RADAR_BACK_LEFT",
                "RADAR_BACK_RIGHT",
            ]

            RADAR_MATRICES = [
                lidar2radar_front,
                lidar2radar_front_left,
                lidar2radar_front_right,
                lidar2radar_back_left,
                lidar2radar_back_right,
            ]

            ego_speed = measurements["speed"]
            full_radar_pcd = []

            for i, radar in enumerate(RADARS):
                radar_pcd = np.fromfile(os.path.join(DATAROOT, radar, ITEM + ".bin"), dtype=np.float32).reshape(-1, 4)
                ranges = radar_pcd[:, 0]
                altitude = radar_pcd[:, 1]
                azimuth = radar_pcd[:, 2]
                velocity = radar_pcd[:, 3]
                # Convert to x, y, z.
                x = ranges * np.cos(azimuth) * np.cos(altitude)
                y = -ranges * np.sin(azimuth) * np.cos(altitude) # VERY IMPORTANT: -y, due to CARLA coordinates.
                z = ranges * np.sin(altitude)

                # Compensate velocity.
                range_unit_vector = np.array([x / ranges, y / ranges]).T

                if i == 0 or i == 3 or i == 4:
                    vr_ego = ego_speed * range_unit_vector[:, 0]
                else:
                    vr_ego = ego_speed * range_unit_vector[:, 1]

                if i == 0 or i == 2:
                    velo_comp = -velocity - vr_ego
                else:
                    velo_comp = velocity - vr_ego

                # Rotate velocity to LiDAR.
                velo_comp_x = velo_comp * range_unit_vector[:, 0]
                velo_comp_y = velo_comp * range_unit_vector[:, 1]
                velo_comp_z = np.zeros_like(velo_comp)
                velo_comp_matrix = np.vstack((velo_comp_x, velo_comp_y, velo_comp_z)).T

                # Radar Rotation.
                radar_rotation = RADAR_MATRICES[i][:3, :3]
                velo_comp_rotated = velo_comp_matrix @ radar_rotation.T

                # Convert to LiDAR coordinates.
                radar_pcd_homogeneous = np.vstack((x, y, z, np.ones_like(x))).T

                RADAR2LIDAR = np.linalg.inv(RADAR_MATRICES[i])
                pcd_radar_lidar = radar_pcd_homogeneous @ RADAR2LIDAR.T

                # Create the final point cloud.
                # Add also azimuth, elevation and range.
                full_radar_pcd.append(np.hstack((pcd_radar_lidar[:, :3], velo_comp_rotated[:, :2], velocity[:, np.newaxis], azimuth[:, np.newaxis], altitude[:, np.newaxis], ranges[:, np.newaxis])))
                
            # Concatenate all radar point clouds for each sample.
            full_radar_pcd = np.vstack(full_radar_pcd)

            # Save the radar point cloud.
            os.makedirs(os.path.join(DATAROOT, "radar_points"), exist_ok=True)
            with open(os.path.join(DATAROOT, "radar_points", ITEM + ".bin"), "wb") as f:
                full_radar_pcd.astype(np.float32).tofile(f)

    print(" ---- CREATING THE SPLITS ---- ")

    total_files = 0

    # Check if train and val files exist.
    # If not, create them empty.
    if not os.path.exists(os.path.join(DATASET_PATH, "train.txt")):
        with open(os.path.join(DATASET_PATH, "train.txt"), "w") as f:
            pass
    else:
        os.remove(os.path.join(DATASET_PATH, "train.txt"))
    if not os.path.exists(os.path.join(DATASET_PATH, "val.txt")):
        with open(os.path.join(DATASET_PATH, "val.txt"), "w") as f:
            pass
    else:
        os.remove(os.path.join(DATASET_PATH, "val.txt"))
    
    # If there is only one route (testing purposes).
    if len(route_names) == 1:
        # Firstly, get the number of the items in the train random split
        DATAROOT = route
        BOXES_PATH = os.path.join(DATAROOT, "boxes")
        MEASUREMENTS_PATH = os.path.join(DATAROOT, "measurements")

        # CHECK COLLISIONS

        # Read number of files in the folders.
        n_files = len([name for name in os.listdir(BOXES_PATH) if os.path.isfile(os.path.join(BOXES_PATH, name))])

        total_files += n_files

        # Get the random split.
        train_files = random.sample(range(n_files), int(n_files*1))
        val_files = [i for i in range(n_files) if i not in train_files]

        # Order files.
        train_files = sorted(train_files)
        val_files = sorted(val_files)
        folder_name = os.path.basename(DATAROOT)

        # Filter out collisions.
        invalid_files = check_collisions(DATAROOT)
        
        # Remove invalid files from train and val (when collision happens).
        train_files = [i for i in train_files if str(i).zfill(4) not in invalid_files]
        val_files = [i for i in val_files if str(i).zfill(4) not in invalid_files]

        # Save to txt files.
        with open(os.path.join(DATASET_PATH, "train.txt"), "a") as f:
            for item in train_files:
                f.write(os.path.join(DATAROOT, str(item).zfill(4)) + "\n")

        with open(os.path.join(DATASET_PATH, "val.txt"), "a") as f:
            for item in val_files:
                f.write(os.path.join(DATAROOT, str(item).zfill(4)) + "\n")

    # If there are multiple routes (most cases), use the predefined training and validation routes.
    else:
        train_folders = []
        val_folders = []
        total_folders = len(route_names)

        for route_name in route_names:
            if "training" in route_name:
                train_folders.append(route_name)
            elif "validation" in route_name:
                val_folders.append(route_name)

        print("Train folders: ", len(train_folders))
        for train_folder in train_folders:
            print("Train folder: ", train_folder.split("/")[-1])
            DATAROOT = train_folder
            BOXES_PATH = os.path.join(DATAROOT, "boxes")
            MEASUREMENTS_PATH = os.path.join(DATAROOT, "measurements")

            # Read number of files in the folders.
            n_files = len([name for name in os.listdir(BOXES_PATH) if os.path.isfile(os.path.join(BOXES_PATH, name))])

            # Check collisions.
            invalid_files = check_collisions(DATAROOT)
            # Remove invalid files from train.
            for i in invalid_files:
                if i in train_folder:
                    invalid_files.remove(i)
            train_files = [i for i in range(n_files) if str(i).zfill(4) not in invalid_files]

            folder_name = os.path.basename(DATAROOT)

            with open(os.path.join(DATASET_PATH, "train.txt"), "a") as f:
                for item in train_files:
                    f.write(os.path.join(DATAROOT, str(item).zfill(4)) + "\n")

        print("\nVal folders: ", len(val_folders))
        for val_folder in val_folders:
            print("Val folder: ", val_folder.split("/")[-1])
            # First, get the number of the items in the val random split.
            DATAROOT = val_folder
            BOXES_PATH = os.path.join(DATAROOT, "boxes")
            MEASUREMENTS_PATH = os.path.join(DATAROOT, "measurements")

            # Read number of files in the folders.
            n_files = len([name for name in os.listdir(BOXES_PATH) if os.path.isfile(os.path.join(BOXES_PATH, name))])

            # Check collisions.
            invalid_files = check_collisions(DATAROOT)
            # Remove invalid files from val.
            for i in invalid_files:
                if i in val_folder:
                    invalid_files.remove(i)
            val_files = [i for i in range(n_files) if str(i).zfill(4) not in invalid_files]

            # From dataroot, get only the folder name.
            folder_name = os.path.basename(DATAROOT)

            with open(os.path.join(DATASET_PATH, "val.txt"), "a") as f:
                for item in val_files:
                    f.write(os.path.join(DATAROOT, str(item).zfill(4)) + "\n")

    # Checking final result.
    with open(os.path.join(DATASET_PATH, "train.txt"), "r") as f:
        train_files = f.readlines()
        train_files = [i.strip() for i in train_files]
        print("\nNumber of train files: ", len(train_files))
    
    with open(os.path.join(DATASET_PATH, "val.txt"), "r") as f:
        val_files = f.readlines()
        val_files = [i.strip() for i in val_files]
        print("Number of val files: ", len(val_files))

    total_files = len(train_files) + len(val_files)
    print("Total samples after filtering: ", total_files)

    # Print global instances and save in a txt using class_dict.
    print("\nGlobal instances of each class:")
    with open(os.path.join(DATASET_PATH, "class_instances.txt"), "w") as f:
        for key, value in class_dict.items():
            print(f"{key}: {value}")
            f.write(f"{key}: {value}\n")
    print("Done!")
    print("Dataset formatted successfully!")

    

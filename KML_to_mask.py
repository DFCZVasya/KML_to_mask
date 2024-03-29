import requests
from io import BytesIO
import math
from math import log, exp, tan, pi
from PIL import Image
import sys
import os
import json
import numpy as np
import cv2
import hashlib
import pickle
import xml.etree.ElementTree as ET


def get_placemarks(path_to_kml):
    """
    extract from kml file placemarks of Polygon type
    prints number of Polygon type objects found
    args:
        path_to_kml - path to kml file
    return:
        Placemarks - list of all placemarks objects found in kml file
        Polygons - list of placemark objects of Polygon type
    """
    tree = ET.parse(path_to_kml)
    root = tree.getroot()
    prefix = '{http://www.opengis.net/kml/2.2}'
    Placemarks = [elem for elem in root[0].iter(prefix + 'Placemark')]
    len(Placemarks)
    Polygons = [elem for elem in Placemarks if (elem.find(prefix + 'Polygon'))]
    print('{} of Polygons found in kml'.format(len(Polygons)))
    return Placemarks, Polygons


def get_polygon_coords(polygon):
    coords = polygon[2][1][0][0].text.split('\n')[1].split('\t\t\t\t\t\t\t')[1].split(' ')
    coords = [coord.split(',')[:2] for coord in coords if coord != '']

    return np.array(coords).astype(np.float)


def get_polygon_bbox(polygon):
    """
    find bounding box for polygon object
    args:
        polygon - polygon object of xml type, exctracted from kml file
    return:
        vertices of bbox, as latitude (top, bottom) and londitude (left, right)
    """
    coords = get_polygon_coords(polygon)
    (left, bottom), (right, top) = coords.min(axis=0), coords.max(axis=0)

    return top, left, bottom, right


def get_polygon_center(polygon):
    """
    find center of polygon bounding box
    args:
        polygon - polygon object of xml type, exctracted from kml file
    return:
        list of centers of bboxes in the same order, as input list of bboxes
    """
    bbox = get_polygon_bbox(polygon)

    return (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2


def get_map_for_POI(lat, long, zoom=17, size=512):
    """
    find center of map with point of interest (POI)
    see for details
    https://stackoverflow.com/questions/47106276/converting-pixels-to-latlng-coordinates-from-google-static-image/47243808#47243808?newreg=cd1977839d544f088003137c5d0e87e7
    args:
        lat - latitude of POI
        long - longitude of POI
        zoom - zoom pf the google map
        size - size in pixels of map, the same in both directions: size x size
            can't be more than 640
    return:
        long, lat - center of map in .7f precision
        zoom, size - unchanged
    """
    C_zoom = 360 / (2 ** (zoom - 1))
    # width and height in pixels of hypothetic image with (bottom, left) = 0, 0
    # and (top, right) = POI
    n_map_long = long / C_zoom
    lat_angle = lat * math.pi / 180
    lat_norm = 180 / math.pi * math.log(1 / math.cos(lat_angle) + math.tan(lat_angle))
    n_map_lat = lat_norm / C_zoom

    # several sucsessive approaches used to dump dependence on latitude in angle
    # first approach to lat degree per image and center map
    lat_Degrees_per_img512 = C_zoom * np.cos(lat_angle)
    center_map_lat = lat + (0.5 - (n_map_lat % 1)) * lat_Degrees_per_img512
    # second approach
    lat_Degrees_per_img512 = C_zoom * np.cos(center_map_lat * math.pi / 180)
    center_map_lat = lat + (0.5 - (n_map_lat % 1)) * lat_Degrees_per_img512
    # third approach
    lat_Degrees_per_img512 = C_zoom * np.cos(center_map_lat * math.pi / 180)
    center_map_lat = lat + (0.5 - (n_map_lat % 1)) * lat_Degrees_per_img512

    lng_Degrees_per_img512 = C_zoom
    center_map_long = long + (0.5 - (n_map_long % 1)) * lng_Degrees_per_img512

    return round(center_map_long, 7), round(center_map_lat, 7), zoom, size


def download_google_maps_by_center(SAVE_DIR, obj2map):
    """
    downloads google maps with center, zoom and size, specified in obj2map list
    map instances with the same center downloaded only once
    maps saved as satellite images in jpg format
    args:
        SAVE_DIR - folder to save
        obj2map - list of maps metadata in format
                  i, center_map_long, center_map_lat, zoom, size, hsh
    return:
        nothing
    """
    names = os.listdir(SAVE_DIR)

    for rec in obj2map:
        [i, center_map_long, center_map_lat, zoom, size, hsh] = rec
        print(center_map_lat, center_map_long)
        name = hsh + '.jpg'
        if name not in names:
            urlparams = {'center': ','.join((str(center_map_lat),
                                             str(center_map_long))),
                         'zoom': str(zoom),
                         'size': str(size) + 'x' + str(size),
                         'maptype': 'satellite',
                         'sensor': 'false',
                         'scale': 1}
            if GOOGLE_MAPS_API_KEY is not None:
                urlparams['key'] = GOOGLE_MAPS_API_KEY
            url = 'http://maps.google.com/maps/api/staticmap'
            try:
                response = requests.get(url, params=urlparams)
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                print(e)
                sys.exit(1)

            im = Image.open(BytesIO(response.content))
            rgb_im = im.convert('RGB')
            save_path = os.path.join(SAVE_DIR, name)
            rgb_im.save(save_path, "JPEG")
            names.append(name)
            print('map lat_{}, long_{} downloaded and saved as {}'.format(center_map_lat,
                                                                          center_map_long,
                                                                          name))


def calc_c_zoom(zoom):
    return 360 / (2 ** (zoom - 1))


def angle_lat(lat):
    return lat * math.pi / 180


def long_degrees_per_pixel(zoom, long):
    return (calc_c_zoom(zoom) / 512)


def lat_degrees_per_pixel(zoom, lat):
    lat_angle = angle_lat(lat)
    return calc_c_zoom(zoom) / 512 * np.cos(lat_angle)


def long_degrees_per_img(zoom, long, size):
    return long_degrees_per_pixel(zoom, long) * size


def lat_degrees_per_img(zoom, lat, size):
    return lat_degrees_per_pixel(zoom, lat) * size


def norm_lat(lat):
    lat_angle = angle_lat(lat)
    return 180 / math.pi * math.log(1 / math.cos(lat_angle) + math.tan(lat_angle))


def get_exact_map_lat(lat, zoom):
    C_zoom = calc_c_zoom(zoom)
    n_map_lat = norm_lat(lat) / C_zoom
    n_map_lat_int = n_map_lat // 1
    diff = (n_map_lat - n_map_lat_int)
    while abs(diff) > 10 ** -9:
        ratio = diff / n_map_lat_int * math.cos(angle_lat(lat)) / lat * norm_lat(lat)
        lat *= (1 - ratio)
        n_map_lat = norm_lat(lat) / C_zoom
        diff = (n_map_lat - n_map_lat_int)
    return lat + lat_degrees_per_img(zoom, lat, size=512) / 2, n_map_lat_int


def get_exact_map_long(long, zoom):
    C_zoom = calc_c_zoom(zoom)
    n_map_long = long / C_zoom
    n_map_long_int = n_map_long // 1
    diff = n_map_long - n_map_long_int
    long *= (1 - diff / n_map_long)
    return long + long_degrees_per_img(zoom, long, size=512) / 2, n_map_long_int


def gl_map_by_center(lat, long, GOOGLE_MAPS_API_KEY,zoom=17, size=640):
    urlparams = {'center': ','.join((str(lat),
                                     str(long))),
                 'zoom': str(zoom),
                 'size': str(size) + 'x' + str(size),
                 'maptype': 'satellite',
                 'sensor': 'false',
                 'scale': 1}
    if GOOGLE_MAPS_API_KEY is not None:
        urlparams['key'] = GOOGLE_MAPS_API_KEY
    url = 'http://maps.google.com/maps/api/staticmap'

    try:
        response = requests.get(url, params=urlparams)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(e)
        sys.exit(1)

    im = Image.open(BytesIO(response.content))
    rgb_im = im.convert('RGB')
    return rgb_im


def obj_to_mask(polygon, exact_map_lat, exact_map_long, zoom, size):
    coords = get_polygon_coords(polygon)
    lat, long = get_polygon_center(polygon)
    top = exact_map_lat + lat_degrees_per_img(zoom, exact_map_lat, size) / 2
    left = exact_map_long - long_degrees_per_img(zoom, exact_map_long, size) / 2

    # convert GPS to pixels
    coords[:, 0] -= left
    coords[:, 0] *= size / long_degrees_per_img(zoom, long, size)
    coords[:, 1] = top - coords[:, 1]
    coords[:, 1] *= size / lat_degrees_per_img(zoom, lat, size)
    coords = coords.astype(np.int32)

    mask_jpg = np.zeros((size, size, 3))
    cv2.drawContours(mask_jpg, [coords], 0, (0, 0, 255), -1)
    mask_png = mask_jpg[:, :, 2]
    return mask_png


def read_kml_and_load_maps(ANNOT_DIR, MAP_DIR, MASKS_DIR,  GOOGLE_MAPS_API_KEY,zoom=17, size=640):
    #read previously saved lists map images or initialize it if not found
    try:
        path_to_map_list = os.path.join(ANNOT_DIR, 'map_list.pickle')
        with open(path_to_map_list, 'rb') as f:
            map_list = pickle.load(f)
    except FileNotFoundError:
        map_list = []

    #load kml files list
    kml_files = [file for file in os.listdir(ANNOT_DIR) if file.endswith('.kml')]
    print(kml_files)

    #make list of already loaded map images
    map_files = os.listdir(MAP_DIR)

    counter = 0

    #initialize polygon objects list
    #it is always constructed from scratch using actual kml data
    obj_list = []

    #scan for masks kml files in ANNOT_DIR
    for kml in kml_files:
        region = kml.split('.kml')[0]
        path_to_kml = os.path.join(ANNOT_DIR, kml)
        print('{} processed...'.format(path_to_kml))
        _, Polygons = get_placemarks(path_to_kml)

        for polygon in Polygons:
            #coordinates of the object's bounding box center
            lat, long = get_polygon_center(polygon)

            #coordinates of the center of the map which contain the center of bbox
            exact_map_lat,  n_map_lat_int =  get_exact_map_lat(lat, zoom)
            exact_map_long, n_map_long_int = get_exact_map_long(long, zoom)

            #create name from coordinates and zoom values
            name = 'lat_{:.7f}_long_{:.7f}_zoom_{}'.format(exact_map_lat, exact_map_long, zoom)
            im_name = name + '.jpg'
            im_path = os.path.join(MAP_DIR, im_name)

            #download maps if is not in MAP_DIR
            if im_name not in map_files:
                im = gl_map_by_center(exact_map_lat, exact_map_long, zoom = zoom, size = size)
                im.save(im_path)
                im = np.array(im)
                print('{} saved'.format(im_path))
                map_files.append(im_name)
                map_list.append([counter, exact_map_long, exact_map_lat, zoom, size, name, region])

            obj_list.append(polygon)
        counter += 1

    path_to_map_list = os.path.join(ANNOT_DIR, 'map_list.pickle')
    with open(path_to_map_list, 'wb') as f:
        pickle.dump(map_list, f)

    path_to_obj_list = os.path.join(ANNOT_DIR, 'obj_list.pickle')
    with open(path_to_obj_list, 'wb') as f:
        pickle.dump(obj_list, f)

def remove_masks_with_ovelapping_pixels(masks_dir):
    files = os.listdir(masks_dir)
    masks = []
    for file in files:
        path = os.path.join(masks_dir, file)
        mask = Image.open(path)
        masks.append([file, np.array(mask)])
    for file_1, mask_1 in masks:
        for file_2, mask_2 in masks:
            if (file_1 != file_2) and (mask_1 & mask_2).any():
                map_1 = file_1.split('_')[:4]
                map_2 = file_2.split('_')[:4]
                if map_1 == map_2:
                    mask_1_num = file_1.split('_')[-1].split('.')[0]
                    mask_2_num = file_2.split('_')[-1].split('.')[0]
                    print('{}, {}'.format(file_1, file_2))
                    if mask_1_num > mask_2_num:
                        rem_path = os.path.join(masks_dir, file_1)
                    else:
                        rem_path = os.path.join(masks_dir, file_2)
                    try:
                        os.remove(rem_path)
                        print('removed {}'.format(rem_path))
                    except:
                        pass

def remove_mask_duplicates(ANNOT_DIR):
    # read list of polygon objects
    path_to_obj_list = os.path.join(ANNOT_DIR, 'obj_list.pickle')
    with open(path_to_obj_list, 'rb') as f:
        old_list = pickle.load(f)

    #initiate new list of non overlapping polygons
    new_list = []
    new_list.append(old_list[0])

    #check polygons for overlap
    for i, old in enumerate(old_list):
        print('\robject {} of {} processed'.format(i, len(old_list)), end='')
        lat, long = get_polygon_center(old)
        old_mask = obj_to_mask(old, lat, long, zoom, size).astype(np.bool)

        overlap = False
        for new in new_list:
            new_mask = obj_to_mask(new, lat, long, zoom, size).astype(np.bool)
            if np.logical_and(old_mask, new_mask).any():
                overlap = True
                print('\noverlap found and removed')

        if not overlap:
            new_list.append(old)

    path_to_obj_list = os.path.join(ANNOT_DIR, 'obj_list.pickle')
    with open(path_to_obj_list, 'wb') as f:
        pickle.dump(new_list, f)
    print('')

def make_masks(ANNOT_DIR, MAP_DIR, CHECK_DIR, MASKS_DIR):
    print('creating masks')

    # read list of map images
    path_to_map_list = os.path.join(ANNOT_DIR, 'map_list.pickle')
    with open(path_to_map_list, 'rb') as f:
        map_list = pickle.load(f)

    # read list of polygon objects
    path_to_obj_list = os.path.join(ANNOT_DIR, 'obj_list.pickle')
    with open(path_to_obj_list, 'rb') as f:
        obj_list = pickle.load(f)

    #initialize mask's counters
    masks_saved = {}

    #check all pairs map - polygon for intersections
    for i, map_rec in enumerate(map_list):
        #read map parameter and load map image
        _, exact_map_long, exact_map_lat, zoom, size, name, region = map_rec
        print('\rmask {} of {} processed'.format(i, len(map_list)), end='')
        im_name = name + '.jpg'
        src_path = os.path.join(MAP_DIR, im_name)
        im = cv2.imread(src_path)

        for polygon in obj_list:

            #create mask of map and polygon
            mask_png = obj_to_mask(polygon, exact_map_lat, exact_map_long, zoom, size)

            #check for non zero mask pixels as a criterion of intersection
            if np.sum(mask_png):
                #counter for masks at the same maps
                try:
                    masks_saved[name] += 1
                except KeyError:
                    masks_saved[name] = 0

                #save mask of polygon
                png_name = name + '_hill_{}.png'.format(masks_saved[name])
                png_path = os.path.join(MASKS_DIR, png_name)
                cv2.imwrite(png_path, mask_png.astype(np.uint8))

                #draw mask on map image
                contours, _ = cv2.findContours(mask_png.astype(np.uint8),cv2.RETR_TREE,cv2.CHAIN_APPROX_SIMPLE)
                cv2.drawContours(im, contours, -1, (255,255,255), 1)

            #save map image in countours of objects
            dst_path = os.path.join(CHECK_DIR, im_name)
            cv2.imwrite(dst_path, im)

    print('masks created and saved')

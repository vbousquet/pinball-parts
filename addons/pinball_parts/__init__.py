#    Copyright (C) 2022  Vincent Bousquet
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>

bl_info = {
    "name": "Pinball Core Part Lib Addon",
    "author": "Vincent Bousquet",
    "version": (0, 0, 1),
    "blender": (3, 2, 0),
    "description": "Tools for the pinball core parts asset library",
    "wiki_url": "",
    "tracker_url": "",
    "support": "COMMUNITY",
    "category": "Import-Export"}

# During development, to reload: bpy.ops.script.reload()

import bpy
import math
import mathutils
import os
from bpy.types import (Operator)


class PCP_OT_render_thumbnail(Operator):
    bl_idname = "pcp.gen_thumbnail"
    bl_label = "Gen. Thumbnail"
    bl_description = "Render a thumbnail for the selected asset"
    bl_options = {"REGISTER", "UNDO"}
    
    @classmethod
    def poll(cls, context):
        return next((o for o in bpy.context.selected_objects if o.asset_data is not None), None) is not None

    def fit_camera(self, camera_object, camera_inclination, obj):
        #if obj.type != 'MESH':
        #    return
        camera_fov = camera_object.data.angle
        camera_angle = math.radians(camera_inclination)
        camera_object.rotation_euler = mathutils.Euler((camera_angle, 0.0, 0.0), 'XYZ')
        camera_object.data.shift_x = 0
        camera_object.data.shift_y = 0
        view_vector = mathutils.Vector((0, math.sin(camera_angle), -math.cos(camera_angle)))
        for i in range(3): # iterations since it depends on the aspect ratio fitting which change after each computation
            # Compute the camera distance with the current aspect ratio
            camera_object.location = (0, 0, 0)
            modelview_matrix = camera_object.matrix_basis.inverted()
            sx = sy = s = 1.0 / math.tan(camera_fov/2.0)
            min_dist = 0
            bbox_corners = [modelview_matrix @ obj.matrix_world @ mathutils.Vector(corner) for corner in obj.bound_box]
            proj_x = map(lambda a: abs(sx * a.x + a.z), bbox_corners)
            proj_y = map(lambda a: abs(sy * a.y + a.z), bbox_corners)
            min_dist = max(min_dist, max(proj_x), max(proj_y))
            camera_object.location.y -= min_dist * view_vector.y
            camera_object.location.z -= min_dist * view_vector.z
            # adjust aspect ratio and compute camera shift to fill the render output
            modelview_matrix = camera_object.matrix_basis.inverted()
            projection_matrix = camera_object.calc_matrix_camera(bpy.context.evaluated_depsgraph_get())
            max_x = max_y = min_x = min_y = 0
            bbox_corners = [projection_matrix @ modelview_matrix @ obj.matrix_world @ mathutils.Vector((corner[0], corner[1], corner[2], 1)) for corner in obj.bound_box]
            proj_x = [o for o in map(lambda a: a.x / a.w, bbox_corners)]
            proj_y = [o for o in map(lambda a: a.y / a.w, bbox_corners)]
            min_x = min(min_x, min(proj_x))
            min_y = min(min_y, min(proj_y))
            max_x = max(max_x, max(proj_x))
            max_y = max(max_y, max(proj_y))
        # Center on render output
        camera_object.data.shift_x = 0.25 * (max_x + min_x)
        camera_object.data.shift_y = 0.25 * (max_y + min_y)

    def execute(self, context):
        objects = [o for o in bpy.context.selected_objects if o.asset_data is not None]
        print(f'Updating asset thumbnails for {len(objects)} assets')

        # Setup basic scene for thumbnail rendering
        scene = bpy.data.scenes.new('Thumbnail Scene')
        camera_data = bpy.data.cameras.new(name='Thumbnail Camera')
        camera_data.clip_start = 0.001
        camera_object = bpy.data.objects.new('Thumbnail  Camera', camera_data)
        scene.collection.objects.link(camera_object)
        scene.camera = camera_object
        scene.world = bpy.context.scene.world
        scene.render.engine = 'CYCLES'
        scene.render.resolution_x = scene.render.resolution_y = 256
        scene.render.film_transparent = True
        scene.render.image_settings.file_format = 'PNG'
        scene.render.image_settings.color_mode = 'RGBA'
        scene.render.image_settings.compression = 25
        tmp_files = []

        for i, obj in enumerate(objects):
            print(f'{i+1}/{len(objects)}: Updating thumbnail for {obj.name}')
            tmp_file = bpy.path.abspath(f'//tmp thumbnail {i+1:3}.png')
            tmp_files.append(tmp_file)
            scene.render.filepath = tmp_file
            scene.collection.objects.link(obj)
            old_pos = obj.matrix_world.copy()
            obj.matrix_world = ((1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0), (0.0, 0.0, 0.0, 1.0))
            self.fit_camera(camera_object, 37.5, obj)
            bpy.ops.render.render(write_still = True, scene=scene.name)
            bpy.ops.ed.lib_id_load_custom_preview({"id": obj}, filepath=tmp_file)
            obj.matrix_world = old_pos
            scene.collection.objects.unlink(obj)
            
        bpy.data.scenes.remove(scene)
        bpy.data.objects.remove(camera_object)
        bpy.data.cameras.remove(camera_data)
        for tmp_file in tmp_files:
            if os.path.exists(tmp_file): os.remove(tmp_file)
        print(f'Done.')
        return {'FINISHED'}


class PCP_PT_3D(bpy.types.Panel):
    bl_label = "Pinball Core Parts"
    bl_category = "PCP"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.operator(PCP_OT_render_thumbnail.bl_idname)


classes = (
    PCP_OT_render_thumbnail,
    PCP_PT_3D,
    )
registered_classes = []


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
        registered_classes.append(cls)


def unregister():
    for cls in registered_classes:
        bpy.utils.unregister_class(cls)
    registered_classes.clear()


if __name__ == "__main__":
    register()
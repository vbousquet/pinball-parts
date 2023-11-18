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
import bmesh
import math
import mathutils
import os
import string
import unicodedata
from bpy.props import (StringProperty)
from bpy.types import (Operator)


def clean_filename(filename):
    whitelist = "-_.() %s%s" % (string.ascii_letters, string.digits)
    
    # keep only valid ascii chars
    cleaned_filename = unicodedata.normalize('NFKD', filename).encode('ASCII', 'ignore').decode()
    
    # keep only whitelisted chars
    cleaned_filename = ''.join(c for c in cleaned_filename if c in whitelist)
    char_limit = 255
    if len(cleaned_filename)>char_limit:
        print("Warning, filename truncated because it was over {}. Filenames may no longer be unique".format(char_limit))
    return cleaned_filename[:char_limit]    


class PCP_OT_set_quality_tag(Operator):
    bl_idname = "pcp.set_quality_tag"
    bl_label = "Quality"
    bl_description = "Set quality tag"
    bl_options = {"REGISTER", "UNDO"}
    tag_name: bpy.props.StringProperty()
    
    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        current_library_name = context.area.spaces.active.params.asset_library_ref
        if current_library_name != "LOCAL":  # NOT Current file
            library_path = Path(context.preferences.filepaths.asset_libraries.get(current_library_name).path)

        for asset_file in context.selected_asset_files:
            if current_library_name == "LOCAL":
                print(f"{asset_file.local_id.name} is selected in the asset browser. (Local File)")
                obj = asset_file.local_id
                # if 'QS' in [tag.name for tag in obj.asset_data.tags]:
                    # obj.asset_data.tags.remove('QS')
                obj.asset_data.tags.new(tag_name)
            else:
                asset_fullpath = library_path / asset_file.relative_path
                print(f"{asset_fullpath} is selected in the asset browser.")
                print(f"It is located in a user library named '{current_library_name}'")

        return {"FINISHED"}


class PCP_OT_render_thumbnail(Operator):
    bl_idname = "pcp.gen_thumbnail"
    bl_label = "Gen. Thumbnail"
    bl_description = "Render a thumbnail for the selected asset"
    bl_options = {"REGISTER", "UNDO"}
    
    # @classmethod
    # def poll(cls, context):
        # return next((o for o in bpy.context.selected_objects if o.asset_data is not None), None) is not None

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
        current_library_name = context.area.spaces.active.params.asset_library_reference
        if current_library_name != "LOCAL":  # NOT Current file
            library_path = Path(context.preferences.filepaths.asset_libraries.get(current_library_name).path)

        objects = []
        for asset in context.selected_assets:
            if current_library_name == "LOCAL":
                print(f"{asset.name} is selected in the asset browser. (Local File)")
                objects.append(asset.local_id)
            else:
                asset_fullpath = library_path / asset. full_library_path
                print(f"{asset_fullpath} is selected in the asset browser.")
                print(f"It is located in a user library named '{current_library_name}'")
        
        #objects = [o for o in bpy.context.selected_objects if o.asset_data is not None]
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
            tmp_file = bpy.path.abspath(f'//thumb - {clean_filename(obj.name)}.png')
            tmp_files.append(tmp_file)
            scene.render.filepath = tmp_file
            if isinstance(obj, bpy.types.Material):
                mesh = bpy.data.meshes.new('Basic_Sphere')
                preview_obj = bpy.data.objects.new("Basic_Sphere", mesh)
                bm = bmesh.new()
                bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=1)
                for f in bm.faces: f.smooth = True
                bm.to_mesh(mesh)
                bm.free()
                preview_obj.data.materials.append(obj)
            elif isinstance(obj, bpy.types.Object):
                preview_obj = obj
            else:
                print(f'Skipping {obj.name} (unsupported type)')
                continue
            scene.collection.objects.link(preview_obj)
            old_pos = preview_obj.matrix_world.copy()
            preview_obj.matrix_world = ((1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0), (0.0, 0.0, 0.0, 1.0))
            self.fit_camera(camera_object, 37.5, preview_obj)
            bpy.ops.render.render(write_still = True, scene=scene.name)
            with bpy.context.temp_override(id=obj):
                bpy.ops.ed.lib_id_load_custom_preview(filepath=tmp_file)
            preview_obj.matrix_world = old_pos
            scene.collection.objects.unlink(preview_obj)
            if preview_obj != obj:
                bpy.data.meshes.remove(preview_obj.data)
            
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
    bl_space_type = "FILE_BROWSER"
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


def draw_thumb_menu(self, context):
    layout = self.layout
    layout.separator()
    layout.operator(PCP_OT_render_thumbnail.bl_idname)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
        registered_classes.append(cls)
    bpy.types.ASSETBROWSER_MT_editor_menus.append(draw_thumb_menu)
    #bpy.types.ASSETBROWSER_MT_context_menu.append(draw_thumb_menu)


def unregister():
    for cls in registered_classes:
        bpy.utils.unregister_class(cls)
    registered_classes.clear()
    bpy.types.ASSETBROWSER_MT_editor_menus.remove(draw_thumb_menu)
    #bpy.types.ASSETBROWSER_MT_context_menu.remove(draw_thumb_menu)


if __name__ == "__main__":
    register()
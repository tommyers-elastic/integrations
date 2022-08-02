from contextlib import closing
import csv
import logging
import os
import requests
import yaml

ECS_VERSION = 8.3
LOG_ONLY = False  # do not modify any files if true

logger = logging.getLogger(__file__)
logger.setLevel('DEBUG')
logger.addHandler(logging.FileHandler('log.txt'))


def get_ecs_field_names_and_types(url=f'https://raw.githubusercontent.com/elastic/ecs/{ECS_VERSION}/generated/csv/fields.csv'):
    """Get all field names and their types from the specified version of ECS."""

    fields = dict()

    with closing(requests.get(url, stream=True)) as r:
        reader = csv.reader(line.decode('utf-8') for line in r.iter_lines())
        headers = next(reader)
        field_idx, type_idx = headers.index('Field'), headers.index('Type')
        for line in reader:
            fields[line[field_idx]] = line[type_idx]

    return fields


def expand_group_field_names(group):
    """Given a group structure with nested fields, return a copy of the group with expanded field names.

    e.g. given the parsed YAML input:

    ```
    - name: cloud
      title: Cloud
      type: group
      fields:
      - name: account.id
        level: extended
        type: keyword
      - name: availability_zone
        level: extended
        type: keyword
    ```

    This function will return

    ```
    [
        {
            'name': 'cloud.account.id',
            'level': 'extended',
            'type': 'keyword'
        },
        {
            'name': 'cloud.availability_zone',
            'level': 'extended',
            'type': 'keyword'
        }
    ]
    ```

    """
    return [{**f, 'name': f'{group["name"]}.{f["name"]}'} for f in group.get('fields', [])]


def is_group(input):
    return input.get('type', '') == 'group'


def get_ecs_fields_to_move(filename, input, ecs_fields):
    fields_to_move, fields_with_different_types = [], []

    for f in input:
        if is_group(f):
            fields_to_move.extend(get_ecs_fields_to_move(filename, expand_group_field_names(f), ecs_fields))
            continue

        if f['name'] not in ecs_fields:
            continue

        if f.get('external', '') == 'ecs' or f['type'] == ecs_fields[f['name']]:
            fields_to_move.append(f['name'])
        else:
            fields_with_different_types.append(f)

    if len(fields_with_different_types) != 0:
        logger.warning(f'In {filename}, the following ECS fields have non-ECS types: '
                       f'{[(f["name"], f["type"], ecs_fields[f["name"]]) for f in fields_with_different_types]}')

    return fields_to_move


def write_to_ecs_file(dir, fields_to_move):
    if LOG_ONLY:
        return

    new_fields = [{'name': f, 'external': 'ecs'} for f in fields_to_move]

    # append the fields we are moving to the ecs.yml file, creating it if it does not exist
    with open(os.path.join(dir, 'ecs.yml'), 'a+') as f:
        f.seek(0)
        existing_fields = yaml.load(f, Loader=yaml.CLoader) or []

        fields_to_write = filter(lambda f: f not in existing_fields, new_fields)

        if len(fields_to_write) != 0:
            f.write(yaml.dump(fields_to_write, Dumper=yaml.CDumper))


def reconstruct_input_file(dir, filename, moved_fields, original_fields):
    if LOG_ONLY:
        return

    new_fields = []

    for f in original_fields:
        if is_group(f):
            # for groups we compare with expanded field names (which is what will be in `moved_fields`),
            # and write back the original group structure with any moved fields filtered out.
            group_fields = []
            for gf in f.get('fields', []):
                if f'{f["name"]}.{gf["name"]}' not in moved_fields:
                    group_fields.append(gf)

            if len(group_fields) != 0:
                new_fields.append({**f, 'fields': group_fields})

        elif f['name'] not in moved_fields:
            new_fields.append(f)

    path = os.path.join(dir, filename)

    if len(new_fields) == 0:
        # no fields left, so remove the input file entirely
        os.remove(path)
    else:
        with open(path, 'w') as f:
            f.write(yaml.dump(new_fields, Dumper=yaml.CDumper))


def move_ecs_fields(dir, filename, ecs_fields):
    """Move ECS fields which are documented in non 'ecs.yml' files into the data stream's 'ecs.yml'.

    This is a 3 step process:
        1. Build a list of fields which need to be moved. If it's empty, return.
        2. Append the fields from step 1 to 'ecs.yml' (avoiding duplication).
        3. Re-write the file with the remaining fields; if there are no fields remaining, delete the file.

    There is some hard-to-grep logic for dealing with groups, but all it's doing is removing nested ECS
    fields in groups and reconstructing the original groups without any loss of information.
    """

    if filename == 'ecs.yml':
        return

    with open(os.path.join(dir, filename), 'r') as fr:
        original_fields = yaml.load(fr, Loader=yaml.CLoader)
        fields_to_move = get_ecs_fields_to_move(filename, original_fields, ecs_fields)

        if len(fields_to_move) == 0:
            return

    logger.debug(f'Moving the following ECS fields to from "{filename}" to "ecs.yml": {fields_to_move}')

    write_to_ecs_file(dir, fields_to_move)
    reconstruct_input_file(dir, filename, fields_to_move, original_fields)


if __name__ == '__main__':
    ecs_fields = get_ecs_field_names_and_types()

    packages_path = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir, 'packages'))
    packages = os.listdir(packages_path)

    for package in packages:
        data_stream_path = os.path.join(packages_path, package, 'data_stream')
        for dir, dirs, files in os.walk(data_stream_path):
            if dir.endswith('fields'):
                logger.info(f'Processing {package}/{dir.split(os.path.sep)[-2]}')
                for f in files:
                    move_ecs_fields(dir, f, ecs_fields)

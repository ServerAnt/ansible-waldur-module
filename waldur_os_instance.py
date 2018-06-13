#!/usr/bin/python
# has to be a full import due to Ansible 2.0 compatibility
from ansible.module_utils.basic import *
from waldur_client import (
    WaldurClientException, ObjectDoesNotExist,
    waldur_full_argument_spec, waldur_client_from_module
)

DOCUMENTATION = '''
---
module: waldur_os_instance
short_description: Create or delete OpenStack instance
version_added: 0.8
description:
  - Create or delete OpenStack compute instance via Waldur API.
requirements:
  - python = 2.7
  - requests
  - python-waldur-client
options:
  access_token:
    description:
      - An access token which has permissions to create an OpenStack instances.
    required: true
  api_url:
    description:
      - Fully qualified url to the Waldur.
    required: true
  data_volume_size:
    description:
      - The size of the data volume in GB. Data volume is not created if value is empty.
    required: false
  flavor:
    description:
      - The name or id of the flavor to use.
        If this is not declared, flavor_min_cpu and/or flavor_min_ram must be declared.
    required: false
  flavor_min_cpu:
    description:
      - The minimum cpu count.
    required: false
  flavor_min_ram:
    description:
      - The minimum ram size (MB).
    required: false
  floating_ip:
    description:
      - An id or address of the existing floating IP to use.
        Not assigned if not specified. Use `auto` to allocate new floating IP or reuse available one.
    required:
      - If a `networks` parameter is not provided.
  image:
    description:
      - The name or id of the image to use.
    required: true
  interval:
    default: 20
    description:
      - An interval of the instance state polling.
  name:
    description:
      - The name of the new OpenStack instance or UUID for existing instance.
    required: true
  networks:
    description:
      - A list of networks an instance has to be attached to.
        A network object consists of 'floating_ip' and 'subnet' fields.
      required:
        - If neither 'floating_ip' nor 'subnet' provided.
  project:
    description:
      - The name or id of the project to add an instance to.
    required: true
  provider:
    description:
      - The name or id of the instance provider.
    required: true
  security_groups:
    default: default
    description:
      - A list of ids or names of security groups to apply to the newly created instance.
    required: false
  ssh_key:
    description:
      - The name or id of the SSH key to attach to the newly created instance.
    required: false
  state:
    choices:
      - present
      - absent
    default: present
    description:
      - Should the resource be present or absent.
  subnet:
    description:
      - The name or id of the subnet to use.
    required:
      - If a `networks` parameter is not provided.
  system_volume_size:
    description:
      - The size of the system volume in GBs.
    required: true
  timeout:
    default: 600
    description:
      - The maximum amount of seconds to wait until the instance provisioning is finished.
  user_data:
    description:
      - An additional data that will be added to the instance on provisioning.
    required: false
  tags:
    description:
      - List of tags that will be added to the instance on provisioning.
    required: false
  wait:
    default: true
    description:
      - A boolean value that defines whether client has to wait until the instance
      provisioning is finished.
'''

EXAMPLES = '''
- name: provision a warehouse instance
  hosts: localhost
  tasks:
    - name: add instance
      waldur_os_instance:
        access_token: b83557fd8e2066e98f27dee8f3b3433cdc4183ce
        api_url: https://waldur.example.com:8000/api
        data_volume_size: 100
        flavor: m1.micro
        image: Ubuntu 16.04 x86_64
        name: Warehouse instance
        networks:
          - floating_ip: auto
            subnet: vpc-1-tm-sub-net
          - floating_ip: 192.101.13.124
            subnet: vpc-1-tm-sub-net-2
        project: OpenStack Project
        provider: VPC
        security_groups:
          - web

- name: provision build instance
  hosts: localhost
  tasks:
    - name: add instance
      waldur_os_instance:
        access_token: b83557fd8e2066e98f27dee8f3b3433cdc4183ce
        api_url: https://waldur.example.com:8000/api
        flavor: m1.micro
        floating_ip: auto
        image: CentOS 7 x86_64
        name: Build instance
        project: OpenStack Project
        provider: VPC
        ssh_key: ssh1.pub
        subnet: vpc-1-tm-sub-net-2
        system_volume_size: 40
        user_data: |-
            #cloud-config
            chpasswd:
              list: |
                ubuntu:{{ default_password }}
              expire: False

- name: Trigger master instance
  hosts: localhost
  tasks:
    - name: add instance
      waldur_os_instance:
        access_token: b83557fd8e2066e98f27dee8f3b3433cdc4183ce
        api_url: https://waldur.example.com:8000/api
        flavor: m1.micro
        floating_ip: auto
        image: CentOS 7 x86_64
        name: Build instance
        project: OpenStack Project
        provider: VPC
        ssh_key: ssh1.pub
        subnet: vpc-1-tm-sub-net-2
        system_volume_size: 40
        tags:
            - ansible_application_id
        wait: false

- name: flavor search by cpu and ram size
  hosts: localhost
  tasks:
    - name: add instance
      waldur_os_instance:
        access_token: b83557fd8e2066e98f27dee8f3b3433cdc4183ce
        api_url: https://waldur.example.com:8000/api
        data_volume_size: 100
        flavor_min_cpu: 2
        flavor_min_ram: 1024
        image: Ubuntu 16.04 x86_64
        name: Warehouse instance
        networks:
          - floating_ip: auto
            subnet: vpc-1-tm-sub-net
          - floating_ip: 192.101.13.124
            subnet: vpc-1-tm-sub-net-2
        project: OpenStack Project
        provider: VPC
        security_groups:
          - web

- name: create OpenStack instance with predefined floating IP
  hosts: localhost
  tasks:
    - name: create instance
      waldur_os_instance:
        access_token: b83557fd8e2066e98f27dee8f3b3433cdc4183ce
        api_url: https://waldur.example.com:8000/api
        project: OpenStack Project
        provider: VPC
        name: Warehouse instance
        image: CentOS 7
        flavor: m1.small
        subnet: vpc-1-tm-sub-net-2
        floating_ip: 1.1.1.1
        system_volume_size: 10

- name: delete existing OpenStack compute instance
  hosts: localhost
  tasks:
    - name: delete instance
      waldur_os_instance:
        access_token: b83557fd8e2066e98f27dee8f3b3433cdc4183ce
        api_url: https://waldur.example.com:8000/api
        project: OpenStack Project
        name: Warehouse instance
        state: absent
'''


def send_request_to_waldur(client, module):
    name = module.params['name']
    project = module.params['project']
    present = module.params['state'] == 'present'

    instance = None
    has_changed = False

    try:
        instance = client.get_instance(name, project)
        if not present:
            client.delete_instance(instance['uuid'])
            has_changed = True
    except ObjectDoesNotExist:
        if present:
            networks = module.params.get('networks') or [{
                'subnet': module.params['subnet'],
                'floating_ip': module.params.get('floating_ip')
            }]

            instance = client.create_instance(
                name=module.params['name'],
                provider=module.params['provider'],
                project=module.params['project'],
                networks=networks,
                image=module.params['image'],
                system_volume_size=module.params['system_volume_size'],
                security_groups=module.params.get('security_groups'),
                flavor=module.params.get('flavor'),
                flavor_min_cpu=module.params.get('flavor_min_cpu'),
                flavor_min_ram=module.params.get('flavor_min_ram'),
                data_volume_size=module.params.get('data_volume_size'),
                ssh_key=module.params.get('ssh_key'),
                wait=module.params['wait'],
                interval=module.params['interval'],
                timeout=module.params['timeout'],
                user_data=module.params.get('user_data'),
                tags=module.params.get('tags'),
                check_mode=module.check_mode,
            )
            has_changed = True

    return instance, has_changed


def main():
    module = AnsibleModule(
        argument_spec=waldur_full_argument_spec(
            name=dict(required=True, type='str'),
            project=dict(type='str', default=None),
            provider=dict(type='str', default=None),
            flavor=dict(type='str', default=None),
            flavor_min_cpu=dict(type='int', default=None),
            flavor_min_ram=dict(type='int', default=None),
            image=dict(type='str', default=None),
            system_volume_size=dict(type='int', default=None),
            security_groups=dict(type='list', default=None),
            networks=dict(type='list', default=None),
            subnet=dict(type='str', default=None),
            floating_ip=dict(type='str', default=None),
            data_volume_size=dict(type='int', default=None),
            ssh_key=dict(type='str', default=None),
            user_data=dict(type='str', default=None),
            tags=dict(type='list', default=None),
            state=dict(default='present', choices=['absent', 'present']),
        ),
        mutually_exclusive=[
            ['subnet', 'networks'],
            ['floating_ip', 'networks'],
            ['flavor_min_cpu', 'flavor'],
            ['flavor_min_ram', 'flavor']
        ],
        supports_check_mode=True,
    )

    state = module.params['state']
    project = module.params['project']
    provider = module.params['provider']
    image = module.params['image']
    flavor = module.params['flavor']
    flavor_min_cpu = module.params['flavor_min_cpu']
    flavor_min_ram = module.params['flavor_min_ram']
    subnet = module.params['subnet']
    networks = module.params['networks']
    system_volume_size = module.params['system_volume_size']

    if state == 'present':
        if not project:
            module.fail_json(msg="Parameter 'project' is required if state == 'present'")
        if not provider:
            module.fail_json(msg="Parameter 'provider' is required if state == 'present'")
        if not image:
            module.fail_json(msg="Parameter 'image' is required if state == 'present'")
        if not (flavor or (flavor_min_cpu and flavor_min_ram)):
            module.fail_json(msg="Parameter 'flavor' or ('flavor_min_cpu' and 'flavor_min_ram')"
                                 " is required if state == 'present'")
        if not system_volume_size:
            module.fail_json(msg="Parameter 'system_volume_size' is required if state == 'present'")
        if not networks and not subnet:
            module.fail_json(msg="Parameter 'networks' or 'subnet' is required if state == 'present'")

    client = waldur_client_from_module(module)
    try:
        instance, has_changed = send_request_to_waldur(client, module)
    except WaldurClientException as error:
        module.fail_json(msg=error.message)
    else:
        module.exit_json(instance=instance, has_changed=has_changed)


if __name__ == '__main__':
    main()

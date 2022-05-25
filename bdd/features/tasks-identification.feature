Feature: Tasks identification
  Here we are not concerned by commenting of migration, just that we identify
    correctly what has to be migrated
  Make sure we identify ansible playbook, plays and tasks files correctly
  Make sure we handle `tasks`, `pre_tasks`, `post_tasks`, `handlers`
  Make sure we handle `block`, `rescue`, `always`

  Background: Set some flags common to most scenarios
    Given I set option "cache_path" to list "./cache"
      And I set flag "no_logs_in_files"

  Scenario: Recognize playbooks
    Given I have the following task
          """
            - hosts: servers
              tasks:
                - name: Make sure java is installed
                  package:
                    name: "{{ openjdk_package_name }}"
                    state: present
                  become: true
          """

      When I migrate

      Then logs must contain "Migrating as playbook file"

  Scenario: Recognize play
    Given I have the following task
          """
              - name: Make sure java is installed
                package:
                  name: "{{ openjdk_package_name }}"
                  state: present
                become: true
          """

      When I migrate

      Then logs must contain "Migrating as play file"

  Scenario: Process tasks, pre_tasks, post_tasks and handlers in a playbook
    Given I have the following task
          """
          - hosts: servers
            pre_tasks:
              - name: pre task
                file:
                  path: "{{ my_temp_file }}"
            tasks:
              - name: Make sure java is installed
                package:
                  name: "{{ openjdk_package_name }}"
                  state: present
            post_tasks:
              - name: post task
                file:
                  path: "{{ my_temp_file }}"
            handlers:
              - name: restart
                service:
                  name: "{{ my_service }}"
          """

      When I migrate

      Then it must be migrated as such
          """
          - hosts: servers
            pre_tasks:
              - name: pre task
                ansible.builtin.file:
                  path: "{{ my_temp_file }}"
            tasks:
              - name: Make sure java is installed
                ansible.builtin.package:
                  name: "{{ openjdk_package_name }}"
                  state: present
            post_tasks:
              - name: post task
                ansible.builtin.file:
                  path: "{{ my_temp_file }}"
            handlers:
              - name: restart
                ansible.builtin.service:
                  name: "{{ my_service }}"
          """
      
      And logs must contain "Migrating as playbook file"


  Scenario: Migrating a builtin task
    Given I have the following task
          """
              - name: "Check for java {{ openjdk_major_version }}.{{ openjdk_minor_version }} install"
                package:
                  name: "{{ openjdk_package_name }}"
                  state: present
                become: true
          """

      When I migrate
      
      Then it must be migrated as such
          """
              - name: "Check for java {{ openjdk_major_version }}.{{ openjdk_minor_version }} install"
                ansible.builtin.package:
                  name: "{{ openjdk_package_name }}"   
                  state: present
                become: true
          """

 Scenario: Process block, rescue, always in a play
    Given I have the following task
          """
            - name: Attempt and graceful roll back demo
              block:
                - name: Print a message
                  debug:
                    msg: 'I execute normally'

                - name: Force a failure
                  command: /bin/false
                  when: true

                - name: Never print this
                  debug:
                    msg: 'I never execute, due to the above task failing'
              rescue:
                - name: Print when errors
                  debug:
                    msg: 'I caught an error'

                - name: Force a failure in middle of recovery! >:-)
                  command: /bin/false
                  when: true

                - name: Never print this
                  debug:
                    msg: 'I also never execute :-('
              always:
                - name: Always do this
                  debug:
                    msg: "This always executes"
          """

      When I migrate

      Then it must be migrated as such
          """
            - name: Attempt and graceful roll back demo
              block:
                - name: Print a message
                  ansible.builtin.debug:
                    msg: 'I execute normally'

                - name: Force a failure
                  ansible.builtin.command: /bin/false
                  when: true

                - name: Never print this
                  ansible.builtin.debug:
                    msg: 'I never execute, due to the above task failing'
              rescue:
                - name: Print when errors
                  ansible.builtin.debug:
                    msg: 'I caught an error'

                - name: Force a failure in middle of recovery! >:-)
                  ansible.builtin.command: /bin/false
                  when: true

                - name: Never print this
                  ansible.builtin.debug:
                    msg: 'I also never execute :-('
              always:
                - name: Always do this
                  ansible.builtin.debug:
                    msg: "This always executes"
          """

 Scenario: Process block, rescue, always in a play in a playbook
    Given I have the following task
          """
          - hosts: servers
            tasks:
              - name: Attempt and graceful roll back demo
                block:
                  - name: Print a message
                    ansible.builtin.debug:
                      msg: 'I execute normally'
                    changed_when: yes
                    notify: run me even after an error

                  - name: Force a failure
                    command: /bin/false
                rescue:
                  - name: Make sure all handlers run
                    meta: flush_handlers
            handlers:
              - name: Run me even after an error
                debug:
                  msg: 'This handler runs even on error'            
          """
       
      When I migrate

      Then it must be migrated as such
          """
          - hosts: servers
            tasks:
              - name: Attempt and graceful roll back demo
                block:
                  - name: Print a message
                    ansible.builtin.debug:
                      msg: 'I execute normally'
                    changed_when: yes
                    notify: run me even after an error

                  - name: Force a failure
                    ansible.builtin.command: /bin/false
                rescue:
                  - name: Make sure all handlers run
                    ansible.builtin.meta: flush_handlers
            handlers:
              - name: Run me even after an error
                ansible.builtin.debug:
                  msg: 'This handler runs even on error'   
          """

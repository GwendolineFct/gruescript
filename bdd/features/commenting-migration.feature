Feature: Commenting tasks migration
  Here we are concerned by the comments that the migration tool outputs in the migrated files
  We also check the migration rules
  
  Background: Set some flags common to most scenarios
    Given I set option "cache_path" to list "./bdd/resources/test.cache.yml"

  Scenario: Correctly migrate a 2.9 module to latest
    Given I have the following task
          """
              - name: Basic test
                basic:
                  param1: "spam"
                  param2: "eggs"
          """

      When I migrate
      
      Then it must be migrated as such
          """
              - name: Basic test
                migration.test.basic:
                  param1: "spam"
                  param2: "eggs"
          """

  Scenario: Inform user that a 2.9 module does not exist in latest version
    Given I have the following task
          """
            - name: obsolete module
              obsolete:
                param1: "spam"
          """

      When I migrate
      
      Then it must be migrated as such
          """
            - name: obsolete module
          # *** MIG ***  ERROR : module `obsolete` does not exist in latest version
              obsolete:
                param1: "spam"
          """

  Scenario: Must preserve existing comments
    Given I have the following task
          """
            - name: obsolete module
              # need to change this
              obsolete:
                param1: "spam"  # what about eegs ?
          """

      When I migrate
      
      Then it must be migrated as such
          """
            - name: obsolete module
              # need to change this
          # *** MIG ***  ERROR : module `obsolete` does not exist in latest version
              obsolete:
                param1: "spam"  # what about eegs ?
          """

  Scenario: Must warn that it can't handle freeform
    Given I have the following task
          """
            - name: freeform module
              freeform: "spam & eggs"
          """

      When I migrate
      
      Then it must be migrated as such
          """
            - name: freeform module
          # *** MIG ***  WARNING : Cannot perform migration checks on free-form parameters
              migration.test.freeform: "spam & eggs"
          """

  Scenario: Must warn when a using an unknown param
    Given I have the following task
          """
            - name: basic module
              basic:
                param1: "spam"
                param2: "eggs"
                param3: "shrubbery"
          """

      When I migrate
      
      Then it must be migrated as such
          """
            - name: basic module
              migration.test.basic:
                param1: "spam"
                param2: "eggs"
          # *** MIG ***  WARNING : Unknown parameter `param3`
                param3: "shrubbery"
          """

  Scenario: Must warn when a param has been removed
    Given I have the following task
          """
            - name: breaking module
              breaking:
                param1: "spam"
                param2: "eggs"
          """

      When I migrate
      
      Then it must be migrated as such
          """
            - name: breaking module
              migration.test.breaking:
                param1: "spam"
          # *** MIG ***  ERROR : unknown module parameter `param2` in latest version
                param2: "eggs"
          """

  Scenario: Must warn when a param has become mandatory
    Given I have the following task
          """
            - name: breaking module
              breaking:
          """

      When I migrate
      
      Then it must be migrated as such
          """
            - name: breaking module
          # *** MIG ***  ERROR : missing parameter `param1` is required in latest version
              migration.test.breaking:
          """

  Scenario: Must warn when a param default value has changed
    Given I have the following task
          """
            - name: default module
              default:
                param1: "spam"
          """

      When I migrate
      
      Then it must be migrated as such
          """
            - name: default module
          # *** MIG ***  WARNING : default value for missing parameter `param2` changed from `Knight` in version 2.9 to `None` in latest version
              migration.test.default:
                param1: "spam"
          """


  Scenario: Must warn when a param type has changed to something not compatible
    Given I have the following task
          """
            - name: types module
              types:
                param1: "spam"
          """

      When I migrate
      
      Then it must be migrated as such
          """
            - name: types module
              migration.test.types:
          # *** MIG ***  WARNING : type of parameter `param1` changed from `string` in version 2.9 to `integer` in latest version
                param1: "spam"
          """


  Scenario: Must warn when a param valid values have been restricted to a list of choices and our value is evaluated
    Given I have the following task
          """
            - name: choices module
              choices:
                param1: "{{ some_var }}"
          """

      When I migrate
      
      Then it must be migrated as such
          """
            - name: choices module
              migration.test.choices:
          # *** MIG ***  WARNING : Possible values for parameter `param1` have been restricted to a closed list of choices in latest version : [`witch`, `shruberry`]
                param1: "{{ some_var }}"
          """

  Scenario: Must warn when a param valid values have been restricted to a smaller list of choices and our value is evaluated
    Given I have the following task
          """
            - name: choices module
              choices:
                param2: "{{ some_var }}"
          """

      When I migrate
      
      Then it must be migrated as such
          """
            - name: choices module
              migration.test.choices:
          # *** MIG ***  WARNING : Some possible values for parameter `param2` have been removed in latest version. Allowed values are : [`spam`, `eggs`]
                param2: "{{ some_var }}"
          """

  Scenario: Must warn when a param value is no more in list of choices
    Given I have the following task
          """
            - name: choices module
              choices:
                param0: "spam"
                param1: "spam"
                param2: "foo"
          """

      When I migrate
      
      Then it must be migrated as such
          """
            - name: choices module
              migration.test.choices:
                param0: "spam"
          # *** MIG ***  ERROR : value `spam` for parameter `param1` is not valid in latest version. Allowed values are : [`witch`, `shruberry`]
                param1: "spam"
          # *** MIG ***  ERROR : value `foo` for parameter `param2` is not valid in latest version. Allowed values are : [`spam`, `eggs`]
                param2: "foo"
          """          
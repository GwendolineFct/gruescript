Feature: Files and folders migration
  Here we are concerned by checking that we can migrate files and folders

  Background: Set some common things for most scenarios
    Given I set option "cache_path" to list "../tests/resources/test.cache.yml"
      And I have empty folder "../tmp/sandbox"

  Scenario: Migrate a single playbook
      Given I have a copy of file "../tests/resources/test-playbook.yml" in folder "../tmp/sandbox"

       When I migrate "../tmp/sandbox"

       Then I must find file "../tmp/sandbox/test-playbook.migrated.yml" that matches "../tests/resources/test-playbook.expected.yml"


  Scenario: Migrate a single play file
      Given I have a copy of file "../tests/resources/test-play.yml" in folder "../tmp/sandbox"

       When I migrate "../tmp/sandbox"

       Then I must find file "../tmp/sandbox/test-play.migrated.yml" that matches "../tests/resources/test-play.expected.yml"


  Scenario: Migrate a single playbook file in replace mode
      Given I have a copy of file "../tests/resources/test-playbook.yml" in folder "../tmp/sandbox"
        And I set option "overwrite_source" to "True"
       When I migrate "../tmp/sandbox"

       Then I must find file "../tmp/sandbox/test-playbook.yml" that matches "../tests/resources/test-playbook.expected.yml"



  Scenario: Migrate a single play file in replace mode
      Given I have a copy of file "../tests/resources/test-play.yml" in folder "../tmp/sandbox"
        And I set option "overwrite_source" to "True"
       When I migrate "../tmp/sandbox"

       Then I must find file "../tmp/sandbox/test-play.yml" that matches "../tests/resources/test-play.expected.yml"


  Scenario: Migrate a directory and it's sub-folder ignoring folders/files starting with a dot (.)
      Given I have a copy of file "../tests/resources/test-playbook.yml" in folder "../tmp/sandbox"
        And I have a copy of file "../tests/resources/test-play.yml" in folder "../tmp/sandbox" with name ".ignore-me.yml" 
        And I have a copy of file "../tests/resources/test-play.yml" in folder "../tmp/sandbox/"
        And I have a copy of file "../tests/resources/test-play.yml" in folder "../tmp/sandbox/folder"
        And I have a copy of file "../tests/resources/test-play.yml" in folder "../tmp/sandbox/.hidden"
        And I set option "overwrite_source" to "True"
       
       When I migrate "../tmp/sandbox"

       Then I must find file "../tmp/sandbox/test-playbook.yml" that matches "../tests/resources/test-playbook.expected.yml"       
       Then I must find file "../tmp/sandbox/test-play.yml" that matches "../tests/resources/test-play.expected.yml"
       Then I must find file "../tmp/sandbox/folder/test-play.yml" that matches "../tests/resources/test-play.expected.yml"
       Then I must find file "../tmp/sandbox/.hidden/test-play.yml" that matches "../tests/resources/test-play.yml"
       Then I must find file "../tmp/sandbox/.ignore-me.yml" that matches "../tests/resources/test-play.yml"



  Scenario: Migrate a directory and it's sub-folder processing folders/files starting with a dot (.)
      Given I have a copy of file "../tests/resources/test-playbook.yml" in folder "../tmp/sandbox"
        And I have a copy of file "../tests/resources/test-play.yml" in folder "../tmp/sandbox" with name ".ignore-me.yml" 
        And I have a copy of file "../tests/resources/test-play.yml" in folder "../tmp/sandbox/"
        And I have a copy of file "../tests/resources/test-play.yml" in folder "../tmp/sandbox/folder"
        And I have a copy of file "../tests/resources/test-play.yml" in folder "../tmp/sandbox/.hidden"
        And I set option "overwrite_source" to "True"
        And I set option "process_hidden_files" to "True"
       
       When I migrate "../tmp/sandbox"

       Then I must find file "../tmp/sandbox/test-playbook.yml" that matches "../tests/resources/test-playbook.expected.yml"       
       Then I must find file "../tmp/sandbox/test-play.yml" that matches "../tests/resources/test-play.expected.yml"
       Then I must find file "../tmp/sandbox/folder/test-play.yml" that matches "../tests/resources/test-play.expected.yml"
       Then I must find file "../tmp/sandbox/.hidden/test-play.yml" that matches "../tests/resources/test-play.expected.yml"
       Then I must find file "../tmp/sandbox/.ignore-me.yml" that matches "../tests/resources/test-play.expected.yml"
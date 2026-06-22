Feature: AI Scene Assembler
  As a non-3D professional user
  I want the AI Agent to automatically fetch and assemble 3D scenes
  So that I can quickly prototype high-quality Blender environments without manual modeling

  Scenario: Setting up HDRI lighting based on fuzzy intent
    Given a blank Blender scene
    When the user requests "give me an evening outdoor vibe"
    Then the Agent should trigger the `hdri_setup` skill
    And semantically translate "evening outdoor vibe" to the Poly Haven API category "sunrise/sunset"
    And download and apply the corresponding HDRI to the World Node

  Scenario: Fetching specific 3D assets
    Given a Blender scene
    When the user requests "I need a vintage wooden table"
    Then the Agent should trigger the `asset_fetcher` skill
    And search the Poly Haven API for models tagged "wood" or "table"
    And download the glTF model
    And import the glTF model into the current scene

  Scenario: Auto-layout of multiple assets
    Given a Blender scene with multiple newly imported assets placed at the origin
    When the user requests to organize the scene
    Then the Agent should trigger the `auto_layout` skill
    And the `auto_layout` skill should invoke the Python script to arrange objects on a grid
    And the LLM should not perform coordinate math directly

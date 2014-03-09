---
title: Fuzzy Folders Help
author: Dean Jackson <deanishe@deanishe.net>
date: 2014-03-09
---

# Fuzzy Folders Alfred Workflow #

Fuzzy search across folder subtrees.

![](https://github.com/deanishe/alfred-fuzzyfolders/raw/master/demo.gif "")

This Workflow provides partial matching of path components, allowing you to drill down into your filesystem with a space-separated query. Each "word" of the query will be matched against the components of a directory's path, so a three-word query will only match at least three levels down from the specified root directory.

You can use a File Action to intiate a fuzzy search on a folder or to assign a keyword to perform a fuzzy search on that folder.

## Commands ##

- `fuzzy` — List your Fuzzy Folders
	+ `↩` — Run the associated keyword
	+ `⌘+↩` — Delete the keyword / Fuzzy Folder combination
- `fzyup` — Recreate the Script Filters from your saved configuration (useful after an update)
- `fzyhelp` — Open the help file in your browser

## File Actions ##

- `Fuzzy Search Here` — Fuzzy search this folder
- `Add Fuzzy Folder` — Set a keyword for this folder for faster searching

## Search result actions ##

- `↩` — Open folder in Finder
- `⌘+↩` — Browse folder in Alfred

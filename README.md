# Fuzzy Folders Alfred Workflow #

Fuzzy search across folder subtrees.

![](https://github.com/deanishe/alfred-fuzzyfolders/raw/master/demo.gif "")

This Workflow provides partial matching of path components, allowing you to drill down into your filesystem with a space-separated query. Each "word" of the query will be matched against the components of a directory or file's path, so a three-word query will only match at least three levels down from the specified root directory.

You can use a **File Action** to intiate a fuzzy search on a folder or to assign a keyword to perform a fuzzy search on that folder.

## Download ##

Get the Workflow from [GitHub](https://github.com/deanishe/alfred-fuzzyfolders/raw/master/Fuzzy%20Folders.alfredworkflow) or [Packal](http://www.packal.org/workflow/fuzzy-folders).

## Commands ##

- `fuzzy` — List your Fuzzy Folders
	+ `↩` — Edit Fuzzy Folder settings
	+ `⌘+↩` — Start a Fuzzy Folder search with the associated keyword
	+ `⌥+↩` — Delete the keyword–Fuzzy Folder combination
- `fzyup` — Recreate the Script Filters from your saved configuration (useful after an update)
- `fzyhelp` — Open the help file in your browser

## Settings ##

You can specify these settings globally as defaults for all Fuzzy Folders or on a per-folder basis. For ad-hoc searches via the `Fuzzy Search Here` file action, the default settings always apply.

Use keyword `fuzzy` to view and edit settings.

- **Minimum query length** — The last "word" of a query must be this long to trigger a search. Default is `1`, but increase this number if the search is too slow. This is very often the case if you're searching a large subtree and/or also choose to search files.
- **Search scope** — Choose to search only for folders, files or both. **Note:** In most cases, searches including files are significantly slower. Consider increasing the **minimum query length** to speed up slow searches.

## File Actions ##

- `Fuzzy Search Here` — Fuzzy search this folder
- `Add Fuzzy Folder` — Set a keyword for this folder for faster fuzzy searching

## Search result actions ##

- `↩` — Open folder in Finder
- `⌘+↩` — Browse folder in Alfred

## Bugs, questions, feedback ##

You can [open an issue on GitHub](https://github.com/deanishe/alfred-fuzzyfolders/issues), or post on the [Alfred Forum](http://www.alfredforum.com/topic/4042-fuzzy-folders/).

## Licensing, other stuff ##

This Workflow is made available under the [MIT Licence](http://opensource.org/licenses/MIT).

The icon was made by [Jono Hunt](http://iconaholic.com/).

It uses [docopt](https://github.com/docopt/docopt) and [Alfred-Workflow](https://github.com/deanishe/alfred-workflow).

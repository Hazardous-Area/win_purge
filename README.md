# Win_purge

It is a very bad idea to run Python code from the internet that modifies the Windows Registry.  Minor bugs in Win_purge can be critical - any could inadvertantly cripple your system.  Win_purge can delete important registry keys if you let it - I do not know the purpose of every Registry key, and there is no special treatment of any Windows edition or setups (the code can quickly become out of date - the frequency of automatic Windows updates in the modern age, means Win_purge could have become inadvertantly unsafe at any point in time).  

I draw your attention to the last paragraph of the MIT license:

"THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE."


That said, if you accept the risk, then win_purge has been designed to take the following steps to protect your system, based on a simple text search:

 - Refuses to run if a matching registered uninstaller is found (as this should be run instead).
 - Uses exactly the same search code for a safe dry run, as for a run that deletes matching keys - no surprising results.
 - Requires a special force switch on the CLI to delete and modify keys.
 - Prompts for confirmation, skip or quit (y/n/quit respectively) before each change.
 - Tries to identify system path keys.  In recognised path keys, win_purge modifies the path name/data in the value instead (removing matching paths from the system wide path and from the user's path).  
 - Backs up each key before modification or deletion (with `reg export`[^0]), and consolidates the backups after each session.
 - Uses send2trash to send the temporary key back up files to the Recycle Bin (does not permanently delete them).

 - Win_purge can also delete matching application files from common installation directories.

 <!-- - Tested? -->

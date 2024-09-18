document.getElementById("sidebarCollapse").addEventListener("click", function() {
    let sidebar = document.getElementById("sidebar");
    let content = document.getElementById("content");

    // Toggle the 'collapsed' class for the sidebar and 'fullwidth' class for the content
    sidebar.classList.toggle('collapsed');
    content.classList.toggle('fullwidth');
});

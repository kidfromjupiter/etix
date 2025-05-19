section => {
    // Extract the performance ID from the current URL
    const performanceId = window.location.pathname.split('/')[3];
    console.log("Performance ID:", performanceId);
    
    // Check if the imageMapfrm exists
    const existingForm = document.getElementById('imageMapfrm');
    
    if (existingForm) {
      // If the form exists, set the necessary values and submit it
      console.log("Using existing form to navigate to manifest");
      
      // Set the selection value if needed
      if (document.querySelector('input[name="selection"]')) {
        document.querySelector('input[name="selection"]').value = section;
      }
      
      // Submit the form
      existingForm.submit();
    } else {
      // Create a new form and submit it
      console.log("Creating new form to navigate to manifest");
      const form = document.createElement('form');
      form.method = 'POST';
      form.action = '/ticket/mvc/legacyOnlineSale/performance/sale/showManifest';
      
      // Add the performance ID
      const perfInput = document.createElement('input');
      perfInput.type = 'hidden';
      perfInput.name = 'performance_id';
      perfInput.value = performanceId;
      form.appendChild(perfInput);
      
      // Add selection method (required parameter)
      const methodInput = document.createElement('input');
      methodInput.type = 'hidden';
      methodInput.name = 'current_selection_method'; 
      methodInput.value = 'byManifest';
      form.appendChild(methodInput);
      
      // Add section selection if needed
      const selectionInput = document.createElement('input');
      selectionInput.type = 'hidden';
      selectionInput.name = 'selection';
      selectionInput.value = section; // From the sectionList array in window context
      form.appendChild(selectionInput);
      
      // Append to body and submit
      document.body.appendChild(form);
      form.submit();
    }
}